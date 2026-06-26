"""OCR service: trích xuất văn bản từ ảnh và PDF.

Engine chính: PaddleOCR (hỗ trợ tiếng Anh tốt, layout tốt).
PDF: thử lấy text layer trực tiếp trước (pypdf), fallback sang render
từng trang -> OCR (pypdfium2) khi PDF là bản scan.

Code tương thích cả PaddleOCR 2.x (API `.ocr(...)`) và 3.x (API `.predict(...)`).
"""

from __future__ import annotations

import io
import os
import re
import time
from typing import Iterable

import numpy as np
from loguru import logger

from app.core.config import get_settings


# Giới hạn cạnh dài nhất của ảnh trước khi đưa vào OCR.
# PaddleOCR mặc định resize cạnh dài về 960 nên >2000px là phí. Hạ về
# ~1600 cân bằng giữa độ chính xác và tốc độ.
_MAX_IMAGE_LONG_EDGE = 1600


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
        self._engine_api: str = ""  # "predict" (3.x) hoặc "ocr" (2.x)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def max_bytes(self) -> int:
        return self._max_bytes

    def _load_engine(self):
        """Lazy-load PPStructureV3. Tránh chi phí import lúc khởi động app."""
        if self._engine_ready:
            return self._engine

        import os
        # Cấu hình cache và temp directories để không tốn dung lượng ổ C:
        os.makedirs('E:\\AI_CACHE\\paddle_ocr\\temp', exist_ok=True)
        os.environ['TEMP'] = 'E:\\AI_CACHE\\paddle_ocr\\temp'
        os.environ['TMP'] = 'E:\\AI_CACHE\\paddle_ocr\\temp'
        os.environ['PADDLE_PDX_CACHE_HOME'] = 'E:\\AI_CACHE\\paddle_ocr'

        try:
            # Workaround conflict DLL trên Windows:
            try:
                import torch  # type: ignore
            except Exception:
                pass

            from paddleocr import PPStructureV3  # type: ignore
            # Khởi tạo pipeline PP-StructureV3 chạy trên GPU (tự động phát hiện)
            self._engine = PPStructureV3()
            self._engine_ready = True
            logger.info("PP-OCRv6 Pipeline (PP-StructureV3) loaded successfully on GPU.")
        except Exception as e:
            logger.error("Không thể load PPStructureV3. Hãy cài paddleocr + paddlepaddle-gpu. Lỗi: {}", e)
            self._engine = None
            self._engine_ready = True
        return self._engine

    def warmup(self) -> None:
        """Pre-warm engine: chạy inference giả để JIT compile + load weights vào RAM.

        Gọi 1 lần khi app startup để request đầu tiên không bị cold start.
        """
        import sys
        if "pytest" in sys.modules:
            logger.info("Chạy trong môi trường test, bỏ qua OCR warmup.")
            return

        try:
            engine = self._load_engine()
            if engine is None:
                return
            # Ảnh trắng nhỏ, chạy qua pipeline
            dummy = np.full((48, 48, 3), 255, dtype=np.uint8)
            t0 = time.perf_counter()
            engine.predict(dummy)
            elapsed = time.perf_counter() - t0
            logger.info("OCR warmup done in {:.2f}s.", elapsed)
        except Exception as e:
            logger.warning("OCR warmup lỗi (bỏ qua): {}", e)

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
            text = self._ocr_image_bytes(data)

        return self._postprocess(text)

    def _ocr_image_bytes(self, data: bytes) -> str:
        engine = self._load_engine()
        if engine is None:
            raise OCRError(
                "OCR engine chưa sẵn sàng. Hãy kiểm tra cài đặt paddleocr + paddlepaddle-gpu."
            )

        import tempfile
        temp_path = None
        try:
            # Tạo file tạm trên ổ E:
            with tempfile.NamedTemporaryFile(dir='E:\\AI_CACHE\\paddle_ocr\\temp', suffix='.png', delete=False) as tf:
                tf.write(data)
                temp_path = tf.name

            t0 = time.perf_counter()
            results = engine.predict(temp_path)
            elapsed = time.perf_counter() - t0

            texts = []
            for res in results:
                if res and hasattr(res, 'markdown') and isinstance(res.markdown, dict):
                    page_text = res.markdown.get('markdown_texts', '')
                    if page_text:
                        texts.append(page_text)
            text = "\n\n".join(texts)

            logger.info(
                "OCR ảnh xong: {} trang, {:.2f}s.",
                len(results),
                elapsed,
            )
            return text
        except Exception as e:
            logger.exception("OCR ảnh lỗi: {}", e)
            raise OCRError("Không thể OCR ảnh này.") from e
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                     os.remove(temp_path)
                except Exception:
                     pass

    @staticmethod
    def _downscale_if_needed(img):
        """Không cần resize thủ công vì PP-StructureV3 tự quản lý tỷ lệ phân tích tốt hơn."""
        return img

    def _run_engine_on_array(self, arr: np.ndarray) -> str:
        engine = self._load_engine()
        if engine is None:
            raise OCRError("OCR engine chưa sẵn sàng.")
        try:
            results = engine.predict(arr)
            texts = [res.markdown.get('markdown_texts', '') for res in results if res.markdown]
            return "\n\n".join(texts)
        except Exception as e:
            logger.exception("PPStructureV3 error on array: {}", e)
            raise OCRError("Không thể OCR ảnh này.") from e

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
                "OCR engine chưa sẵn sàng. Hãy kiểm tra cài đặt paddleocr + paddlepaddle-gpu."
            )

        import tempfile
        temp_path = None
        try:
            # Tạo file tạm trên ổ E:
            with tempfile.NamedTemporaryFile(dir='E:\\AI_CACHE\\paddle_ocr\\temp', suffix='.pdf', delete=False) as tf:
                tf.write(data)
                temp_path = tf.name

            t0 = time.perf_counter()
            results = engine.predict(temp_path)
            elapsed = time.perf_counter() - t0

            texts = []
            for i, res in enumerate(results[:max_pages]):
                if res and hasattr(res, 'markdown') and isinstance(res.markdown, dict):
                    page_text = res.markdown.get('markdown_texts', '')
                    if page_text:
                        texts.append(f"[Trang {i + 1}]\n{page_text}")
            text = "\n\n".join(texts)

            logger.info(
                "OCR PDF xong: {} trang, {:.2f}s.",
                len(results),
                elapsed,
            )
            return text
        except Exception as e:
            logger.exception("OCR PDF lỗi: {}", e)
            raise OCRError("Không thể OCR PDF này.") from e
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                     os.remove(temp_path)
                except Exception:
                     pass

    @staticmethod
    def _postprocess(text: str) -> str:
        if not text:
            return ""
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


ocr_service = OCRService()

