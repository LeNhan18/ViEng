"""OCR: không cần Paddle/GPU — engine giả cho cả API 3.x (predict) và 2.x (ocr)."""

import io
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from app.services import ocr_service as mod
from app.services.ocr_service import OCRError, OCRService


def _png(w=2400, h=1200) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "white").save(buf, format="PNG")
    return buf.getvalue()


def _scanned_pdf(pages: int) -> bytes:
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    pdf = canvas.Canvas(buf)
    for _ in range(pages):
        pdf.rect(50, 50, 100, 100)  # chỉ hình, không có text layer
        pdf.showPage()
    pdf.save()
    return buf.getvalue()


def _svc(engine, api):
    svc = OCRService()
    svc._enabled = True
    svc._engine, svc._engine_api, svc._engine_ready = engine, api, True
    return svc


def test_no_hardcoded_machine_paths():
    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "E:\\\\" not in src and "os.environ['TEMP']" not in src


def test_image_in_memory_and_downscaled_structure_api():
    seen = []

    class Engine:
        def predict(self, arr):
            seen.append(arr)
            return [SimpleNamespace(markdown={"markdown_texts": "The manager  reviewed\n\n\n\nthe report."})]

    out = _svc(Engine(), "structure").extract_text(_png(), content_type="image/png")
    assert out == "The manager reviewed\n\nthe report."
    assert isinstance(seen[0], np.ndarray) and max(seen[0].shape[:2]) == 1600


def test_paddleocr2_fallback_parsing():
    class Engine:
        def ocr(self, arr, cls=True):
            return [[[[0, 0], ("Hello", 0.99)], [[0, 1], ("world", 0.97)]]]

    assert _svc(Engine(), "ocr").extract_text(_png(200, 100), content_type="image/png") == "Hello\nworld"


def test_scanned_pdf_truncated_before_ocr(monkeypatch):
    from pypdf import PdfReader

    monkeypatch.setattr(mod.get_settings(), "ocr_max_pdf_pages", 3)
    seen = {}

    class Engine:
        def predict(self, path):
            seen["pages"] = len(PdfReader(path).pages)
            seen["path"] = path
            return [SimpleNamespace(markdown={"markdown_texts": "" if i == 1 else f"page{i}"}) for i in range(3)]

    out = _svc(Engine(), "structure").extract_text(_scanned_pdf(8), content_type="application/pdf")
    assert seen["pages"] == 3                      # chỉ gửi 3/8 trang
    assert not Path(seen["path"]).exists()         # file tạm đã xoá
    assert out == "[Trang 1]\npage0\n\n[Trang 3]\npage2"  # số trang không lệch khi có trang trống


def test_scanned_pdf_with_paddleocr2(monkeypatch):
    monkeypatch.setattr(mod.get_settings(), "ocr_max_pdf_pages", 2)
    calls = []

    class Engine:
        def ocr(self, arr, cls=True):
            calls.append(arr.shape)
            return [[[[0, 0], (f"line{len(calls)}", 0.9)]]]

    out = _svc(Engine(), "ocr").extract_text(_scanned_pdf(5), content_type="application/pdf")
    assert len(calls) == 2
    assert out == "[Trang 1]\nline1\n\n[Trang 2]\nline2"


def test_corrupt_image_is_user_error():
    with pytest.raises(OCRError):
        _svc(object(), "structure").extract_text(b"not an image", content_type="image/png")


def test_engine_missing_is_user_error(monkeypatch):
    svc = _svc(None, "")
    with pytest.raises(OCRError):
        svc.extract_text(_png(10, 10), content_type="image/png")
