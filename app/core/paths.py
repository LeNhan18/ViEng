"""Giải quyết đường dẫn cache/temp theo cách chạy được trên Windows, Linux và Docker.

Trước đây cache/temp của OCR bị hard-code vào ổ ``E:\\AI_CACHE`` nên app chỉ chạy
được trên đúng một máy. Module này tập trung mọi quyết định về đường dẫn:

- Gốc cache lấy từ ``VIENG_CACHE_DIR`` (hoặc ``Settings.cache_dir``); nếu trống thì
  dùng ``./data/cache`` để đồng bộ với quy ước ``./data/vectorstore`` đang có.
- Mọi thư mục con (OCR temp, Paddle cache, HuggingFace cache) nằm dưới gốc đó và
  đều có thể ghi đè riêng bằng env.
- Hàm ``ensure_dir`` tự fallback sang thư mục tạm của hệ điều hành khi gốc cache
  không ghi được (ví dụ container mount read-only), để OCR không chết hẳn.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from loguru import logger

_DEFAULT_CACHE_SUBDIR = Path("data") / "cache"
_FALLBACK_NAME = "vieng-cache"


def _first_env(*names: str) -> str:
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def cache_root(configured: str = "") -> Path:
    """Gốc cache: tham số > env VIENG_CACHE_DIR > ./data/cache."""
    raw = (configured or "").strip() or _first_env("VIENG_CACHE_DIR")
    if raw:
        return Path(raw).expanduser()
    return Path(_DEFAULT_CACHE_SUBDIR)


def ensure_dir(path: Path | str) -> Path:
    """Tạo thư mục; nếu không ghi được thì fallback sang thư mục tạm của OS.

    Trả về đường dẫn thực sự dùng được. Không raise để một thư mục cache hỏng
    không làm sập cả request.
    """
    candidate = Path(path).expanduser()
    try:
        candidate.mkdir(parents=True, exist_ok=True)
        probe = candidate / ".write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return candidate
    except OSError as e:
        fallback = Path(tempfile.gettempdir()) / _FALLBACK_NAME / candidate.name
        logger.warning(
            "Không ghi được thư mục cache {} ({}). Dùng tạm {}.", candidate, e, fallback
        )
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def ocr_temp_dir(configured: str = "", cache_dir: str = "") -> Path:
    raw = (configured or "").strip() or _first_env("VIENG_OCR_TEMP_DIR")
    base = Path(raw).expanduser() if raw else cache_root(cache_dir) / "ocr" / "temp"
    return ensure_dir(base)


def paddle_cache_dir(configured: str = "", cache_dir: str = "") -> Path:
    raw = (configured or "").strip() or _first_env("VIENG_PADDLE_CACHE_DIR")
    base = Path(raw).expanduser() if raw else cache_root(cache_dir) / "paddle"
    return ensure_dir(base)


def hf_cache_dir(configured: str = "", cache_dir: str = "") -> Path:
    """Cache HuggingFace/sentence-transformers.

    Tôn trọng HF_HOME nếu người dùng đã đặt sẵn, để không ghi đè cấu hình máy.
    """
    raw = (configured or "").strip() or _first_env("VIENG_HF_CACHE_DIR", "HF_HOME")
    base = Path(raw).expanduser() if raw else cache_root(cache_dir) / "huggingface"
    return ensure_dir(base)


def configure_ocr_env(ocr_temp: Path, paddle_cache: Path) -> None:
    """Trỏ TEMP/TMP/PADDLE_PDX_CACHE_HOME vào thư mục đã tạo được.

    Chỉ gọi ngay trước khi load engine OCR (không gọi ở import time) để không
    ảnh hưởng tới tiến trình khác.
    """
    os.environ["TEMP"] = str(ocr_temp)
    os.environ["TMP"] = str(ocr_temp)
    os.environ["PADDLE_PDX_CACHE_HOME"] = str(paddle_cache)


def configure_hf_env(hf_cache: Path) -> None:
    """Đặt HF_HOME nếu chưa có, để model embedding tải về đúng chỗ."""
    os.environ.setdefault("HF_HOME", str(hf_cache))
