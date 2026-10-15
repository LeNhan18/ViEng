"""OCR service: trích xuất văn bản từ ảnh và PDF.

Engine:
- PaddleOCR 3.x `PPStructureV3` (layout + markdown, GPU nếu có) — mặc định.
- Fallback PaddleOCR 2.x `PaddleOCR(...).ocr(...)` khi không có PP-StructureV3
  (vd. image lite đang pin paddleocr<3).

PDF: thử text layer (pypdf) trước; PDF scan mới OCR, và chỉ OCR tối đa
OCR_MAX_PDF_PAGES trang đầu (cắt PDF trước khi đưa vào engine).

Không hardcode đường dẫn theo máy: thư mục tạm = OCR_TEMP_DIR hoặc thư mục tạm
của hệ điều hành; cache model = OCR_MODEL_CACHE_DIR (nếu đặt).
"""

from __future__ import annotations

import io
import os
import re
import tempfile
import threading
import time

import numpy as np
from loguru import logger

from app.core.config import get_settings

# PaddleOCR resize cạnh dài về ~960; ảnh >1600px chỉ tốn thời gian.
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
        self._engine_api: str = ""  # "structure" (PPStructureV3) | "ocr" (PaddleOCR 2.x)
        # Engine Paddle không thread-safe: tuần tự hoá load + inference.
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def max_bytes(self) -> int:
        return self._max_bytes

    # ------------------------------------------------------------------
    # Engine
    # ------------------------------------------------------------------
    @staticmethod
    def _temp_dir() -> str:
        d = get_settings().ocr_temp_dir or os.path.join(tempfile.gettempdir(), "vieng_ocr")
        os.makedirs(d, exist_ok=True)
        return d

    def _load_engine(self):
        """Lazy-load engine. Thử PPStructureV3 trước, rồi PaddleOCR 2.x."""
        if self._engine_ready:
            return self._engine
        with self._lock:
            if self._engine_ready:
                return self._engine
            cache_dir = get_settings().ocr_model_cache_dir
            if cache_dir:
                os.makedirs(cache_dir, exist_ok=True)
                os.environ.setdefault("PADDLE_PDX_CACHE_HOME", cache_dir)
                os.environ.setdefault("PADDLEOCR_HOME", cache_dir)

            try:
                try:  # Workaround conflict DLL trên Windows khi có torch
                    import torch  # type: ignore  # noqa: F401
                except Exception:
                    pass
                from paddleocr import PPStructureV3  # type: ignore

                self._engine = PPStructureV3()
                self._engine_api = "structure"
                logger.info("OCR engine: PP-StructureV3 (PaddleOCR 3.x).")
            except ImportError:
                try:
                    from paddleocr import PaddleOCR  # type: ignore

                    self._engine = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
                    self._engine_api = "ocr"
                    logger.info("OCR engine: PaddleOCR 2.x (fallback, không có PP-StructureV3).")
                except Exception as e:
                    logger.error("Không load được PaddleOCR: {}", e)
                    self._engine = None
            except Exception as e:
                logger.error("Không load được PPStructureV3: {}", e)
                self._engine = None
            self._engine_ready = True
        return self._engine

    def _require_engine(self):
        engine = self._load_engine()
        if engine is None:
            raise OCRError("OCR engine chưa sẵn sàng. Hãy kiểm tra cài đặt paddleocr + paddlepaddle.")
        return engine

    @staticmethod
    def _structure_texts(results) -> list[str]:
        texts = []
        for res in results or []:
            md = getattr(res, "markdown", None)
            if isinstance(md, dict):
                t = md.get("markdown_texts", "")
                if t:
                    texts.append(t)
        return texts

    @staticmethod
    def _ocr2_text(result) -> str:
        """Kết quả PaddleOCR 2.x: [[ [box, (text, score)], ... ]] (mỗi ảnh 1 phần tử, có thể None)."""
        lines = []
        for page in result or []:
            for item in page or []:
                try:
                    lines.append(str(item[1][0]))
                except (IndexError, TypeError):
                    continue
        return "\n".join(lines)

    def _run_on_array(self, arr: np.ndarray) -> str:
        engine = self._require_engine()
        with self._lock:
            if self._engine_api == "ocr":
                return self._ocr2_text(engine.ocr(arr, cls=True))
            return "\n\n".join(self._structure_texts(engine.predict(arr)))

    def warmup(self) -> None:
        """Pre-warm engine để request đầu tiên không bị cold start."""
        import sys

        if "pytest" in sys.modules:
            logger.info("Chạy trong môi trường test, bỏ qua OCR warmup.")
            return
        try:
            if self._load_engine() is None:
                return
            t0 = time.perf_counter()
            self._run_on_array(np.full((48, 48, 3), 255, dtype=np.uint8))
            logger.info("OCR warmup done in {:.2f}s.", time.perf_counter() - t0)
        except Exception as e:
            logger.warning("OCR warmup lỗi (bỏ qua): {}", e)

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------
    @staticmethod
    def is_supported(content_type: str | None, filename: str | None) -> bool:
        ct = (content_type or "").lower().strip()
        if ct in _SUPPORTED_IMAGE_TYPES or ct in _PDF_TYPES:
            return True
        name = (filename or "").lower()
        return name.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".pdf"))

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
            raise OCRError(f"File vượt quá giới hạn {self._max_bytes // (1024 * 1024)}MB.")
        if not self.is_supported(content_type, filename):
            raise OCRError("Định dạng không hỗ trợ. Cho phép ảnh (PNG/JPG/WEBP/BMP/TIFF) hoặc PDF.")

        if self._is_pdf(content_type, filename):
            text = self._extract_from_pdf(data)
        else:
            text = self._ocr_image_bytes(data)
        return self._postprocess(text)

    @staticmethod
    def _image_to_array(data: bytes) -> np.ndarray:
        from PIL import Image, ImageOps

        try:
            img = Image.open(io.BytesIO(data))
            img = ImageOps.exif_transpose(img).convert("RGB")
        except Exception as e:
            raise OCRError("Không đọc được ảnh (file hỏng hoặc sai định dạng).") from e
        long_edge = max(img.size)
        if long_edge > _MAX_IMAGE_LONG_EDGE:
            scale = _MAX_IMAGE_LONG_EDGE / long_edge
            img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))))
        return np.asarray(img)

    def _ocr_image_bytes(self, data: bytes) -> str:
        """OCR ảnh trong bộ nhớ (không ghi file tạm)."""
        arr = self._image_to_array(data)
        t0 = time.perf_counter()
        try:
            text = self._run_on_array(arr)
        except OCRError:
            raise
        except Exception as e:
            logger.exception("OCR ảnh lỗi: {}", e)
            raise OCRError("Không thể OCR ảnh này.") from e
        logger.info("OCR ảnh xong: {}x{}px, {:.2f}s.", arr.shape[1], arr.shape[0], time.perf_counter() - t0)
        return text

    # ------------------------------------------------------------------
    # PDF
    # ------------------------------------------------------------------
    def _extract_from_pdf(self, data: bytes) -> str:
        text = self._try_pdf_text_layer(data)
        if text and len(text.strip()) >= self._min_pdf_text_chars:
            logger.info("PDF có text layer, dùng trực tiếp ({} ký tự).", len(text))
            return text
        logger.info("PDF không có text layer hoặc quá ngắn, fallback sang OCR.")
        return self._ocr_pdf_pages(data, max_pages=get_settings().ocr_max_pdf_pages)

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

    @staticmethod
    def _first_pages(data: bytes, max_pages: int) -> tuple[bytes, int]:
        """Cắt PDF còn max_pages trang đầu. Trả về (pdf_bytes, tổng số trang gốc)."""
        try:
            from pypdf import PdfReader, PdfWriter

            reader = PdfReader(io.BytesIO(data))
            total = len(reader.pages)
            if total <= max_pages:
                return data, total
            writer = PdfWriter()
            for page in reader.pages[:max_pages]:
                writer.add_page(page)
            buf = io.BytesIO()
            writer.write(buf)
            return buf.getvalue(), total
        except Exception as e:
            logger.warning("Không cắt được PDF ({}), OCR toàn bộ.", e)
            return data, -1

    def _ocr_pdf_pages(self, data: bytes, max_pages: int = 10) -> str:
        engine = self._require_engine()
        data, total = self._first_pages(data, max_pages)
        if total > max_pages:
            logger.info("PDF {} trang, chỉ OCR {} trang đầu.", total, max_pages)
        t0 = time.perf_counter()
        try:
            if self._engine_api == "ocr":
                pages = self._render_pdf(data, max_pages)
                texts = []
                for i, arr in enumerate(pages):
                    with self._lock:
                        t = self._ocr2_text(engine.ocr(arr, cls=True))
                    if t:
                        texts.append(f"[Trang {i + 1}]\n{t}")
            else:
                texts = self._structure_pdf(engine, data, max_pages)
        except OCRError:
            raise
        except Exception as e:
            logger.exception("OCR PDF lỗi: {}", e)
            raise OCRError("Không thể OCR PDF này.") from e
        logger.info("OCR PDF xong: {} trang có chữ, {:.2f}s.", len(texts), time.perf_counter() - t0)
        return "\n\n".join(texts)

    def _structure_pdf(self, engine, data: bytes, max_pages: int) -> list[str]:
        fd, path = tempfile.mkstemp(suffix=".pdf", dir=self._temp_dir())
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            with self._lock:
                results = list(engine.predict(path))
            texts = []
            for i, res in enumerate(results[:max_pages]):
                page = self._structure_texts([res])
                if page:
                    texts.append(f"[Trang {i + 1}]\n{page[0]}")
            return texts
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    @staticmethod
    def _render_pdf(data: bytes, max_pages: int) -> list[np.ndarray]:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(data)
        out = []
        for i in range(min(len(pdf), max_pages)):
            img = pdf[i].render(scale=2).to_pil().convert("RGB")
            out.append(np.asarray(img))
        return out

    @staticmethod
    def _postprocess(text: str) -> str:
        if not text:
            return ""
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


ocr_service = OCRService()
