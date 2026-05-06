"""OCR service: trích xuất văn bản từ ảnh và PDF.

Engine chính: RapidOCR (ONNX Runtime) - nhẹ, đa nền tảng, hỗ trợ tiếng Anh.
PDF: thử lấy text layer trực tiếp trước (pypdf), fallback sang render
từng trang -> OCR (pypdfium2) khi PDF là bản scan.
"""

from __future__ import annotations

import io
import re
from typing import Iterable

from loguru import logger

from app.core.config import get_settings


_SUPPORTED_IMAGE_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "image/bmp",
    "image/tiff",
}

_PDF_TYPES = {"application/pdf"}


class OCRError(Exception):
    """Lỗi nghiệp vụ OCR (file không hỗ trợ, engine chưa cài, v.v.)."""


class OCRService:
    """OCR service tái sử dụng được, lazy-load engine để khởi động nhanh."""

    def __init__(self) -> None:
        settings = get_settings()
        self._enabled = bool(settings.ocr_enabled)
        self._max_bytes = max(1, settings.ocr_max_file_size_mb) * 1024 * 1024
        self._min_pdf_text_chars = 80
        self._engine = None  # type: ignore[assignment]
        self._engine_ready = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def max_bytes(self) -> int:
        return self._max_bytes

    def _load_engine(self):
        """Lazy-load RapidOCR. Tránh chi phí import lúc khởi động app."""
        if self._engine_ready:
            return self._engine
        try:
            from rapidocr_onnxruntime import RapidOCR  # type: ignore

            self._engine = RapidOCR()
            self._engine_ready = True
            logger.info("RapidOCR engine loaded.")
        except Exception as e:
            logger.error(
                "Không thể load RapidOCR. Hãy cài rapidocr-onnxruntime. Lỗi: {}", e
            )
            self._engine = None
            self._engine_ready = True
        return self._engine

    @staticmethod
    def is_supported(content_type: str | None, filename: str | None) -> bool:
        ct = (content_type or "").lower().strip()
        if ct in _SUPPORTED_IMAGE_TYPES or ct in _PDF_TYPES:
            return True
        # Fallback theo phần mở rộng (một số trình duyệt gửi content_type rỗng).
        name = (filename or "").lower()
        return name.endswith(
            (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".pdf")
        )

    @staticmethod
    def _is_pdf(content_type: str | None, filename: str | None) -> bool:
        ct = (content_type or "").lower().strip()
        if ct in _PDF_TYPES:
            return True
        return (filename or "").lower().endswith(".pdf")

    def extract_text(
        self,
        data: bytes,
        *,
        content_type: str | None = None,
        filename: str | None = None,
    ) -> str:
        """Entry chính: trả về văn bản đã trích xuất (đã làm sạch sơ bộ)."""
        if not self._enabled:
            raise OCRError("OCR đang bị tắt (OCR_ENABLED=false).")
        if not data:
            raise OCRError("File rỗng.")
        if len(data) > self._max_bytes:
            raise OCRError(
                f"File vượt quá giới hạn {self._max_bytes // (1024 * 1024)}MB."
            )
        if not self.is_supported(content_type, filename):
            raise OCRError(
                "Định dạng không hỗ trợ. Cho phép ảnh (PNG/JPG/WEBP/BMP/TIFF) hoặc PDF."
            )

        if self._is_pdf(content_type, filename):
            text = self._extract_from_pdf(data)
        else:
            text = self._extract_from_image(data)

        return self._postprocess(text)

    def _extract_from_image(self, data: bytes) -> str:
        engine = self._load_engine()
        if engine is None:
            raise OCRError(
                "OCR engine chưa sẵn sàng. Cài rapidocr-onnxruntime và thử lại."
            )
        try:
            # RapidOCR chấp nhận numpy.ndarray, đường dẫn file, hoặc bytes.
            result, _elapse = engine(data)
        except Exception as e:
            logger.exception("RapidOCR error: {}", e)
            raise OCRError("Không thể OCR ảnh này.") from e

        return self._join_rapidocr_result(result)

    def _extract_from_pdf(self, data: bytes) -> str:
        text = self._try_pdf_text_layer(data)
        if text and len(text.strip()) >= self._min_pdf_text_chars:
            logger.info("PDF có text layer, dùng trực tiếp ({} ký tự).", len(text))
            return text

        logger.info("PDF không có text layer hoặc quá ngắn, fallback sang OCR.")
        return self._ocr_pdf_pages(data)

    @staticmethod
    def _try_pdf_text_layer(data: bytes) -> str:
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            chunks: list[str] = []
            for page in reader.pages:
                try:
                    chunks.append(page.extract_text() or "")
                except Exception:
                    continue
            return "\n\n".join(c for c in chunks if c)
        except Exception as e:
            logger.warning("Không đọc được text layer PDF: {}", e)
            return ""

    def _ocr_pdf_pages(self, data: bytes, max_pages: int = 10) -> str:
        engine = self._load_engine()
        if engine is None:
            raise OCRError(
                "OCR engine chưa sẵn sàng. Cài rapidocr-onnxruntime và thử lại."
            )
        try:
            import pypdfium2 as pdfium  # type: ignore
        except Exception as e:
            logger.error("pypdfium2 chưa cài để render PDF scan: {}", e)
            raise OCRError(
                "Để OCR PDF dạng scan cần cài thêm pypdfium2."
            ) from e

        pdf = pdfium.PdfDocument(data)
        total_pages = min(len(pdf), max_pages)
        all_text: list[str] = []
        try:
            for i in range(total_pages):
                page = pdf[i]
                # 200 DPI = scale ~2.78 so với 72 DPI mặc định.
                pil_image = page.render(scale=2.78).to_pil()
                buf = io.BytesIO()
                pil_image.save(buf, format="PNG")
                buf.seek(0)
                try:
                    result, _elapse = engine(buf.read())
                    page_text = self._join_rapidocr_result(result)
                except Exception as inner:
                    logger.warning("Lỗi OCR trang {}: {}", i + 1, inner)
                    page_text = ""
                if page_text:
                    all_text.append(f"[Trang {i + 1}]\n{page_text}")
        finally:
            try:
                pdf.close()
            except Exception:
                pass

        return "\n\n".join(all_text)

    @staticmethod
    def _join_rapidocr_result(result: Iterable | None) -> str:
        """RapidOCR trả về list[[box, text, score]] (hoặc None khi không có chữ)."""
        if not result:
            return ""
        lines: list[str] = []
        for item in result:
            try:
                # item = (box, text, score)
                _, text, _score = item[0], item[1], item[2]
            except Exception:
                continue
            if isinstance(text, str) and text.strip():
                lines.append(text.strip())
        return "\n".join(lines)

    @staticmethod
    def _postprocess(text: str) -> str:
        if not text:
            return ""
        # Chuẩn hóa khoảng trắng + xóa dòng rỗng thừa.
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


ocr_service = OCRService()
