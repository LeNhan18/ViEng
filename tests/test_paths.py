"""Test app/core/paths.py: cache/temp dir chạy được trên Windows, Ubuntu và Docker.

Hồi quy cho bug cũ: ocr_service hard-code 'E:\\AI_CACHE\\paddle_ocr\\temp' nên
app chỉ chạy được trên đúng một máy Windows.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from app.core import paths

WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in (
        "VIENG_CACHE_DIR", "VIENG_OCR_TEMP_DIR",
        "VIENG_PADDLE_CACHE_DIR", "VIENG_HF_CACHE_DIR", "HF_HOME",
    ):
        monkeypatch.delenv(var, raising=False)


def test_default_cache_root_is_relative_and_portable():
    root = paths.cache_root()
    assert not WINDOWS_DRIVE.match(str(root)), "mặc định không được gắn ổ đĩa Windows"
    assert not Path(root).is_absolute()


def test_cache_root_prefers_argument_then_env(monkeypatch, tmp_path):
    monkeypatch.setenv("VIENG_CACHE_DIR", str(tmp_path / "from_env"))
    assert paths.cache_root() == tmp_path / "from_env"
    # tham số (từ Settings) thắng env
    assert paths.cache_root(str(tmp_path / "from_arg")) == tmp_path / "from_arg"


def test_subdirs_live_under_cache_root(tmp_path):
    base = str(tmp_path / "cache")
    assert paths.ocr_temp_dir(cache_dir=base) == tmp_path / "cache" / "ocr" / "temp"
    assert paths.paddle_cache_dir(cache_dir=base) == tmp_path / "cache" / "paddle"
    assert paths.hf_cache_dir(cache_dir=base) == tmp_path / "cache" / "huggingface"


def test_subdirs_are_created(tmp_path):
    d = paths.ocr_temp_dir(cache_dir=str(tmp_path / "c"))
    assert d.is_dir()
    # và ghi được
    (d / "x.txt").write_text("y", encoding="utf-8")


def test_explicit_override_wins(tmp_path, monkeypatch):
    custom = tmp_path / "custom_ocr"
    assert paths.ocr_temp_dir(str(custom), cache_dir=str(tmp_path / "c")) == custom
    monkeypatch.setenv("VIENG_OCR_TEMP_DIR", str(tmp_path / "env_ocr"))
    assert paths.ocr_temp_dir(cache_dir=str(tmp_path / "c")) == tmp_path / "env_ocr"


def test_hf_cache_respects_existing_hf_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HOME", str(tmp_path / "hf"))
    assert paths.hf_cache_dir(cache_dir=str(tmp_path / "c")) == tmp_path / "hf"


def test_ensure_dir_falls_back_when_unwritable(tmp_path, monkeypatch):
    """Gốc cache không ghi được -> fallback thư mục tạm OS, không raise."""
    target = tmp_path / "blocked" / "sub"

    real_mkdir = Path.mkdir

    def fake_mkdir(self, *a, **k):
        if "blocked" in str(self):
            raise PermissionError("read-only fs")
        return real_mkdir(self, *a, **k)

    monkeypatch.setattr(Path, "mkdir", fake_mkdir)
    got = paths.ensure_dir(target)
    assert got.is_dir()
    assert "blocked" not in str(got)


def test_configure_ocr_env_points_at_created_dirs(tmp_path, monkeypatch):
    monkeypatch.delenv("PADDLE_PDX_CACHE_HOME", raising=False)
    ocr = paths.ocr_temp_dir(cache_dir=str(tmp_path / "c"))
    paddle = paths.paddle_cache_dir(cache_dir=str(tmp_path / "c"))
    paths.configure_ocr_env(ocr, paddle)
    assert os.environ["TEMP"] == str(ocr)
    assert os.environ["TMP"] == str(ocr)
    assert os.environ["PADDLE_PDX_CACHE_HOME"] == str(paddle)
    assert not WINDOWS_DRIVE.match(os.environ["TEMP"])


def test_configure_hf_env_does_not_clobber(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HOME", "/already/set")
    paths.configure_hf_env(tmp_path / "other")
    assert os.environ["HF_HOME"] == "/already/set"


def test_no_hardcoded_windows_paths_in_source():
    """Hồi quy: không file .py nào trong app/ được hard-code ổ đĩa Windows."""
    offenders = []
    for py in Path("app").rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for m in re.finditer(r"['\"][A-Za-z]:[\\\\/]{1,2}[A-Za-z0-9_]", text):
            offenders.append(f"{py}: {m.group(0)}")
    assert offenders == [], f"đường dẫn ổ đĩa cố định còn sót: {offenders}"


def test_embedding_model_default_is_a_repo_id():
    """Hồi quy: mặc định phải là repo id HF, không phải tên thư mục cache."""
    from app.core.config import Settings

    default = Settings.model_fields["embedding_model"].default
    assert "models--" not in default, "đây là tên thư mục cache HF, không phải repo id"
    assert not WINDOWS_DRIVE.match(default)
    assert default.count("/") == 1
