"""Test tích hợp các chức năng chạy local, KHÔNG gọi LLM/TTS thật.

DB: SQLite (aiosqlite) qua DATABASE_URL — cùng ORM/code với MySQL.
Redis: server thật nếu REDIS_TEST_PORT (mặc định 6380) đang chạy, nếu không dùng fakeredis.
LLM: thay bằng hàm giả ghi lại history được truyền vào.
"""

from __future__ import annotations

import functools
import io
import socket

import pytest
import redis as redis_sync
from fastapi.testclient import TestClient

import app.db.database as dbm
import app.main as main_mod
from app.core.config import get_settings
from app.services.chat_memory_service import chat_memory_service
from app.services.llm_service import llm_service
from app.services.ocr_service import ocr_service
from app.services.rag_service import rag_service

REDIS_PORT = 6380


@functools.lru_cache(maxsize=1)
def _real_redis_available() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", REDIS_PORT), timeout=0.3):
            return True
    except OSError:
        return False


@pytest.fixture
def env(monkeypatch, tmp_path):
    db_file = tmp_path / "vieng_test.db"
    monkeypatch.setenv("USE_DATABASE", "true")
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_file}")
    monkeypatch.setenv("USE_REDIS", "true")
    monkeypatch.setenv("REDIS_PORT", str(REDIS_PORT))
    monkeypatch.setenv("REDIS_DB", "15")
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret-test-secret-123")
    get_settings.cache_clear()
    dbm._engine, dbm._session_factory = None, None

    chat_memory_service.settings = get_settings()
    chat_memory_service._redis_client = None
    if _real_redis_available():
        sync_r = redis_sync.Redis(port=REDIS_PORT, db=15, decode_responses=True)
        sync_r.flushdb()
        backend = "redis-server"
    else:
        import fakeredis

        server = fakeredis.FakeServer()
        sync_r = fakeredis.FakeRedis(server=server, decode_responses=True)
        fake_async = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
        monkeypatch.setattr(chat_memory_service, "get_redis_client", lambda: fake_async)
        backend = "fakeredis"

    monkeypatch.setattr(rag_service, "_enabled", False)
    monkeypatch.setattr(main_mod.settings, "rag_enabled", False)
    monkeypatch.setattr(main_mod.settings, "ocr_enabled", False)

    seen_histories: list[list[dict]] = []

    async def fake_chat(message, history, rag_context="", *, llm_provider=None):
        seen_histories.append([dict(h) for h in history])
        return f"reply to: {message}"

    monkeypatch.setattr(llm_service, "chat", fake_chat)

    with TestClient(main_mod.app) as client:
        yield {"client": client, "redis": sync_r, "histories": seen_histories, "backend": backend}

    sync_r.flushdb()
    get_settings.cache_clear()
    dbm._engine, dbm._session_factory = None, None
    chat_memory_service.settings = get_settings()
    chat_memory_service._redis_client = None


def _register(c, email="lan@example.com", password="password123"):
    return c.post("/api/v1/auth/register", json={"email": email, "password": password})


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------- DB + auth ----------------
def test_db_status_ok(env):
    assert env["client"].get("/api/v1/db/status").json() == {"status": "ok", "database": "connected"}


def test_register_login_me(env):
    c = env["client"]
    r = _register(c, "Lan@Example.com ")
    assert r.status_code == 200
    token = r.json()["access_token"]

    me = c.get("/api/v1/auth/me", headers=_auth(token))
    assert me.status_code == 200
    assert me.json()["email"] == "lan@example.com"  # chuẩn hoá lowercase + strip

    assert _register(c, "lan@example.com").status_code == 409
    assert c.post("/api/v1/auth/login", json={"email": "lan@example.com", "password": "wrong-pass"}).status_code == 401
    ok = c.post("/api/v1/auth/login", json={"email": "LAN@example.com", "password": "password123"})
    assert ok.status_code == 200 and ok.json()["access_token"]


@pytest.mark.parametrize("headers,expected", [
    ({}, 401),
    ({"Authorization": "Bearer not-a-jwt"}, 401),
])
def test_me_rejects_missing_or_bad_token(env, headers, expected):
    assert env["client"].get("/api/v1/auth/me", headers=headers).status_code == expected


def test_register_validation(env):
    c = env["client"]
    assert _register(c, "no-at-sign", "password123").status_code == 400
    assert _register(c, "a@b.co", "short").status_code == 422


# ---------------- chat memory (Redis + DB) ----------------
def test_chat_memory_roundtrip(env):
    c, r = env["client"], env["redis"]
    token = _register(c).json()["access_token"]
    me_id = c.get("/api/v1/auth/me", headers=_auth(token)).json()["id"]
    key = f"vieng:chat_history:{me_id}"

    assert c.post("/api/v1/chat", json={"message": "since hay for?"}, headers=_auth(token)).status_code == 200
    assert c.post("/api/v1/chat", json={"message": "cho ví dụ"}, headers=_auth(token)).status_code == 200

    # LLM lần 2 nhận được lịch sử lần 1 (đọc từ memory, không phải từ client)
    second = env["histories"][1]
    assert [m["content"] for m in second] == ["since hay for?", "reply to: since hay for?", "cho ví dụ"][:len(second)]
    assert second[0]["content"] == "since hay for?"

    hist = c.get("/api/v1/chat/history", headers=_auth(token)).json()
    assert [(m["role"], m["content"]) for m in hist] == [
        ("user", "since hay for?"), ("assistant", "reply to: since hay for?"),
        ("user", "cho ví dụ"), ("assistant", "reply to: cho ví dụ"),
    ]
    assert r.llen(key) == 4

    # Redis mất dữ liệu -> đọc từ DB và đồng bộ lại Redis
    r.delete(key)
    hist2 = c.get("/api/v1/chat/history", headers=_auth(token)).json()
    assert len(hist2) == 4
    assert r.llen(key) == 4

    # Xoá lịch sử ở cả Redis và DB
    assert c.delete("/api/v1/chat/history", headers=_auth(token)).status_code == 200
    assert c.get("/api/v1/chat/history", headers=_auth(token)).json() == []
    assert r.llen(key) == 0


def test_chat_history_isolated_per_user(env):
    c = env["client"]
    t1 = _register(c, "a@example.com").json()["access_token"]
    t2 = _register(c, "b@example.com").json()["access_token"]
    c.post("/api/v1/chat", json={"message": "của A"}, headers=_auth(t1))
    assert c.get("/api/v1/chat/history", headers=_auth(t2)).json() == []
    assert len(c.get("/api/v1/chat/history", headers=_auth(t1)).json()) == 2


def test_anonymous_chat_is_stateless(env):
    c = env["client"]
    r = c.post("/api/v1/chat", json={"message": "hi", "history": [{"role": "user", "content": "trước đó"}]})
    assert r.status_code == 200
    assert env["histories"][-1] == [{"role": "user", "content": "trước đó"}]
    assert env["redis"].keys("vieng:chat_history:*") == []
    assert c.get("/api/v1/chat/history").status_code == 401


def test_redis_keeps_last_100_messages(env):
    c, r = env["client"], env["redis"]
    token = _register(c).json()["access_token"]
    uid = c.get("/api/v1/auth/me", headers=_auth(token)).json()["id"]
    for i in range(55):
        c.post("/api/v1/chat", json={"message": f"m{i}"}, headers=_auth(token))
    assert r.llen(f"vieng:chat_history:{uid}") == 100


# ---------------- OCR (không cần GPU): PDF có text layer ----------------
def _text_pdf(text: str) -> bytes:
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    pdf = canvas.Canvas(buf)
    y = 800
    for line in text.split("\n"):
        pdf.drawString(72, y, line)
        y -= 18
    pdf.save()
    return buf.getvalue()


@pytest.fixture
def ocr_on(monkeypatch):
    monkeypatch.setattr(ocr_service, "_enabled", True)


def test_ocr_pdf_text_layer(env, ocr_on):
    body = "\n".join(["The manager reviewed the quarterly report before the meeting."] * 3)
    files = {"file": ("note.pdf", _text_pdf(body), "application/pdf")}
    r = env["client"].post("/api/v1/ocr", files=files)
    assert r.status_code == 200, r.text
    assert "quarterly report" in r.json()["extracted_text"]


def test_ocr_rejects_bad_input(env, ocr_on, monkeypatch):
    c = env["client"]
    assert c.post("/api/v1/ocr", files={"file": ("a.txt", b"hello", "text/plain")}).status_code == 400
    assert c.post("/api/v1/ocr", files={"file": ("a.pdf", b"", "application/pdf")}).status_code == 400
    monkeypatch.setattr(ocr_service, "_max_bytes", 10)
    big = c.post("/api/v1/chat/ocr", files={"file": ("a.pdf", b"x" * 11, "application/pdf")})
    assert big.status_code == 413


def test_ocr_disabled_returns_503(env, monkeypatch):
    monkeypatch.setattr(ocr_service, "_enabled", False)
    r = env["client"].post("/api/v1/ocr", files={"file": ("a.pdf", b"%PDF", "application/pdf")})
    assert r.status_code == 503


# ---------------- middleware ----------------
def test_api_key_middleware(env, monkeypatch):
    c = env["client"]
    monkeypatch.setattr(main_mod.settings, "api_key", "k-123")
    assert c.get("/api/v1/health").status_code == 200  # health luôn mở
    assert c.get("/api/v1/metrics").status_code == 401
    assert c.get("/api/v1/metrics", headers={"X-API-Key": "k-123"}).status_code == 200


def test_metrics_and_timing_header(env):
    c = env["client"]
    r = c.get("/api/v1/health")
    assert int(r.headers["X-Process-Time-ms"]) >= 0
    m = c.get("/api/v1/metrics").json()
    assert m["http"]["GET /api/v1/health"]["count"] >= 1


# ---------------- chat: lưu sau khi thành công, streaming ----------------
def test_failed_llm_leaves_no_orphan_message(env, monkeypatch):
    c, r = env["client"], env["redis"]
    token = _register(c).json()["access_token"]

    async def boom(*a, **k):
        raise RuntimeError("LLM down")

    monkeypatch.setattr(llm_service, "chat", boom)
    assert c.post("/api/v1/chat", json={"message": "hỏi"}, headers=_auth(token)).status_code == 500
    assert c.get("/api/v1/chat/history", headers=_auth(token)).json() == []
    assert r.keys("vieng:chat_history:*") == []


def test_llm_receives_only_recent_window(env):
    c = env["client"]
    token = _register(c).json()["access_token"]
    for i in range(8):
        c.post("/api/v1/chat", json={"message": f"m{i}"}, headers=_auth(token))
    assert len(env["histories"][-1]) == llm_service.CHAT_HISTORY_WINDOW


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    import json as _json

    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        events.append((lines["event"], _json.loads(lines["data"])))
    return events


def test_chat_stream_sse_and_memory(env, monkeypatch):
    c = env["client"]
    token = _register(c).json()["access_token"]

    async def fake_stream(message, history, rag_context="", *, llm_provider=None):
        for part in ["Since ", "+ mốc ", "thời gian."]:
            yield part

    monkeypatch.setattr(llm_service, "chat_stream", fake_stream)
    monkeypatch.setattr(llm_service, "ensure_configured", lambda: None)
    with c.stream("POST", "/api/v1/chat/stream", json={"message": "since?"}, headers=_auth(token)) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = "".join(resp.iter_text())
    events = _parse_sse(body)
    assert [e for e, _ in events] == ["meta", "delta", "delta", "delta", "done"]
    assert events[-1][1]["message"] == "Since + mốc thời gian."
    hist = c.get("/api/v1/chat/history", headers=_auth(token)).json()
    assert [(m["role"], m["content"]) for m in hist] == [
        ("user", "since?"), ("assistant", "Since + mốc thời gian."),
    ]


def test_chat_stream_error_event_and_no_save(env, monkeypatch):
    c = env["client"]
    token = _register(c).json()["access_token"]

    async def broken(message, history, rag_context="", *, llm_provider=None):
        yield "nửa câu"
        raise RuntimeError("cut")

    monkeypatch.setattr(llm_service, "chat_stream", broken)
    monkeypatch.setattr(llm_service, "ensure_configured", lambda: None)
    with c.stream("POST", "/api/v1/chat/stream", json={"message": "x"}, headers=_auth(token)) as resp:
        body = "".join(resp.iter_text())
    events = _parse_sse(body)
    assert events[-1][0] == "error" and "lỗi hệ thống" in events[-1][1]["detail"]
    assert c.get("/api/v1/chat/history", headers=_auth(token)).json() == []


def test_chat_stream_503_without_llm(env, monkeypatch):
    monkeypatch.setattr(llm_service, "_client", None)
    monkeypatch.setattr(type(llm_service), "_use_finetuned", property(lambda self: False))
    r = env["client"].post("/api/v1/chat/stream", json={"message": "x"})
    assert r.status_code == 503


# ---------------- cache TTS / translate ----------------
def test_tts_cached_in_redis(env, monkeypatch):
    import sys
    import types

    calls = []

    class FakeCommunicate:
        def __init__(self, text, voice):
            calls.append((text, voice))

        async def stream(self):
            yield {"type": "audio", "data": b"ID3fake-mp3"}

    monkeypatch.setitem(sys.modules, "edge_tts", types.SimpleNamespace(Communicate=FakeCommunicate))
    c = env["client"]
    r1 = c.post("/api/v1/tts", json={"text": "Hello   world"})
    r2 = c.post("/api/v1/tts", json={"text": "Hello world"})
    assert r1.content == r2.content == b"ID3fake-mp3"
    assert (r1.headers["X-Cache"], r2.headers["X-Cache"]) == ("MISS", "HIT")
    assert calls == [("Hello world", "en-US-AriaNeural")]
    assert env["redis"].keys("vieng:cache:tts:*")


def test_translate_cached_only_when_complete(env, monkeypatch):
    calls = []

    async def fake_translate(text, direction, level, rag_context="", *, llm_provider=None):
        calls.append(text)
        if text == "fallback":
            return {"translated": "raw", "vocabulary": [], "grammar_notes": []}
        return {"translated": "Xin chào", "vocabulary": [{"word": "hello", "meaning": "xin chào", "example": "Hi"}],
                "grammar_notes": []}

    monkeypatch.setattr(llm_service, "translate", fake_translate)
    c = env["client"]
    body = {"text": "Hello", "direction": "en_to_vi", "level": "beginner"}
    assert c.post("/api/v1/translate", json=body).json()["translated"] == "Xin chào"
    assert c.post("/api/v1/translate", json=body).json()["translated"] == "Xin chào"
    assert calls == ["Hello"]
    # Khác trình độ -> khác key
    c.post("/api/v1/translate", json={**body, "level": "advanced"})
    assert calls == ["Hello", "Hello"]
    # Bản fallback (thiếu từ vựng/ngữ pháp) không được cache
    fb = {**body, "text": "fallback"}
    c.post("/api/v1/translate", json=fb)
    c.post("/api/v1/translate", json=fb)
    assert calls.count("fallback") == 2
    m = c.get("/api/v1/metrics").json()["cache"]
    assert m["translate:hit"]["count"] == 1
