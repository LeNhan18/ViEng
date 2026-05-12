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
        """Lazy-load PaddleOCR. Tránh chi phí import lúc khởi động app."""
        if self._engine_ready:
            return self._engine

        # Workaround conflict DLL trên Windows: PaddlePaddle load oneDNN/MKL
        # version khác torch, nếu Paddle load trước thì torch import sau
        # bị `WinError 127 - shm.dll`. Force-import torch sớm (nếu có) để
        # giữ thứ tự load DLL hợp lệ. Trong chế độ lite (không có torch),
        # bỏ qua nhánh này hoàn toàn.
        try:
            import torch  # noqa: F401  # type: ignore
        except Exception:
            pass

        # Cấu hình hiệu năng:
        # - enable_mkldnn=True: dùng oneDNN trên CPU, tăng tốc 2-3x.
        # - cpu_threads: tận dụng đa nhân (mặc định 10).
        # - use_angle_cls=False: ảnh đề thi hiếm khi xoay 180°, tắt classifier
        #   tiết kiệm 1 model + ~30% latency. Bật lại nếu cần xử lý ảnh xoay.
        cpu_threads = max(2, (os.cpu_count() or 4))

        try:
            from paddleocr import PaddleOCR  # type: ignore

            # Cố gắng khởi tạo theo API 3.x trước (kwargs mới),
            # rơi về kwargs 2.x khi fail (nhiều unexpected keyword).
            try:
                self._engine = PaddleOCR(
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                    lang="en",
                )
                self._engine_api = (
                    "predict" if hasattr(self._engine, "predict") else "ocr"
                )
            except TypeError:
                self._engine = PaddleOCR(
                    use_angle_cls=False,
                    lang="en",
                    show_log=False,
                    enable_mkldnn=True,
                    cpu_threads=cpu_threads,
                )
                self._engine_api = "ocr"

            self._engine_ready = True
            logger.info(
                "PaddleOCR engine loaded (api={}, mkldnn=on, threads={}).",
                self._engine_api,
                cpu_threads,
            )
        except Exception as e:
            logger.error(
                "Không thể load PaddleOCR. "
                "Hãy cài paddleocr + paddlepaddle. Lỗi: {}",
                e,
            )
            self._engine = None
            self._engine_ready = True
        return self._engine

    def warmup(self) -> None:
        """Pre-warm engine: chạy inference giả để JIT compile + load weights vào RAM.

        Gọi 1 lần khi app startup để request đầu tiên không bị cold start.
        """
        try:
            engine = self._load_engine()
            if engine is None:
                return
            # Ảnh trắng nhỏ, OCR sẽ trả rỗng nhưng warm hết các graph.
            dummy = np.full((48, 320, 3), 255, dtype=np.uint8)
            t0 = time.perf_counter()
            self._run_engine_on_array(dummy)
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
                "OCR engine chưa sẵn sàng. Cài paddleocr + paddlepaddle và thử lại."
            )
        try:
            from PIL import Image
        except Exception as e:
            raise OCRError("Thiếu Pillow để decode ảnh.") from e
        try:
            img = Image.open(io.BytesIO(data))
            img.load()
            if img.mode != "RGB":
                img = img.convert("RGB")
            img = self._downscale_if_needed(img)
            arr = np.array(img)
        except Exception as e:
            logger.exception("Decode ảnh lỗi: {}", e)
            raise OCRError("Không đọc được ảnh đầu vào.") from e

        t0 = time.perf_counter()
        text = self._run_engine_on_array(arr)
        elapsed = time.perf_counter() - t0
        logger.info(
            "OCR ảnh xong: {}x{}, {} dòng, {:.2f}s.",
            arr.shape[1],
            arr.shape[0],
            len(text.splitlines()) if text else 0,
            elapsed,
        )
        return text

    @staticmethod
    def _downscale_if_needed(img):
        """Resize ảnh nếu cạnh dài vượt _MAX_IMAGE_LONG_EDGE.

        OCR ảnh quá lớn không cải thiện chính xác (PaddleOCR tự resize về 960
        ở tầng detection) nhưng tốn rất nhiều CPU cho việc decode/copy.
        """
        try:
            from PIL import Image
        except Exception:
            return img
        w, h = img.size
        long_edge = max(w, h)
        if long_edge <= _MAX_IMAGE_LONG_EDGE:
            return img
        ratio = _MAX_IMAGE_LONG_EDGE / float(long_edge)
        new_w = max(1, int(w * ratio))
        new_h = max(1, int(h * ratio))
        try:
            return img.resize((new_w, new_h), Image.LANCZOS)
        except Exception:
            return img

    def _run_engine_on_array(self, arr: np.ndarray) -> str:
        engine = self._load_engine()
        if engine is None:
            raise OCRError("OCR engine chưa sẵn sàng.")

        try:
            if self._engine_api == "predict":
                output = engine.predict(arr)
                return self._join_paddle_predict_output(output)
            # PaddleOCR 2.x: ocr(img, cls=True)
            try:
                result = engine.ocr(arr, cls=True)
            except TypeError:
                # Một số bản 2.x mới đã bỏ cls kwarg.
                result = engine.ocr(arr)
            return self._join_paddle_v2_result(result)
        except Exception as e:
            logger.exception("PaddleOCR error: {}", e)
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
                "OCR engine chưa sẵn sàng. Cài paddleocr + paddlepaddle và thử lại."
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
                if pil_image.mode != "RGB":
                    pil_image = pil_image.convert("RGB")
                arr = np.array(pil_image)
                try:
                    page_text = self._run_engine_on_array(arr)
                except OCRError as inner:
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
    def _join_paddle_v2_result(result: Iterable | None) -> str:
        """PaddleOCR 2.x: result = [[ [box, (text, score)], ... ]] (list per image)."""
        if not result:
            return ""
        lines: list[str] = []
        try:
            # result là list theo từng ảnh. Mình truyền 1 ảnh nên lấy phần tử 0.
            page_items = result[0] if result and isinstance(result, list) else result
        except Exception:
            page_items = result

        if not page_items:
            return ""
        for item in page_items:
            try:
                # item = [box, (text, score)]
                _, txt_pair = item[0], item[1]
                if isinstance(txt_pair, (list, tuple)) and txt_pair:
                    text = txt_pair[0]
                else:
                    text = txt_pair
            except Exception:
                continue
            if isinstance(text, str) and text.strip():
                lines.append(text.strip())
        return "\n".join(lines)

    @staticmethod
    def _join_paddle_predict_output(output) -> str:
        """PaddleOCR 3.x: output là list[OCRResult]; mỗi OCRResult có rec_texts."""
        if not output:
            return ""
        lines: list[str] = []
        try:
            iterable = output if isinstance(output, list) else [output]
        except Exception:
            iterable = [output]

        for res in iterable:
            # Trường hợp dict-like (3.x kiểu object) hoặc dict thật
            texts = None
            if hasattr(res, "rec_texts"):
                texts = getattr(res, "rec_texts", None)
            elif isinstance(res, dict):
                texts = res.get("rec_texts") or res.get("texts")
            if not texts:
                # Fallback: thử lấy json/dict
                try:
                    d = res.json if hasattr(res, "json") else None
                    if isinstance(d, dict):
                        texts = d.get("rec_texts") or d.get("texts")
                except Exception:
                    pass
            if not texts:
                continue
            for t in texts:
                if isinstance(t, str) and t.strip():
                    lines.append(t.strip())
        return "\n".join(lines)

    @staticmethod
    def _postprocess(text: str) -> str:
        if not text:
            return ""
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


ocr_service = OCRService()
