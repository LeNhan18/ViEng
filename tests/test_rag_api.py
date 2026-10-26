"""Test endpoint RAG: readiness, khoá quản trị, và trạng thái truy xuất."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.services.rag_service import RagStatus, RetrievalResult


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


class FakeDoc:
    def __init__(self, content, metadata=None):
        self.page_content = content
        self.metadata = metadata or {}


# ------------------------------------------------------------------ readiness

def test_ready_is_ok_in_lite_mode(client, monkeypatch):
    """RAG tắt chủ động = lite mode, vẫn ready (app chạy được, chỉ không có RAG)."""
    import app.services.rag_service as mod

    monkeypatch.setattr(
        mod.rag_service, "status",
        lambda: {"status": "disabled", "enabled": False, "ready": False,
                 "embedder": "not_loaded", "embedding_model": "x",
                 "index": {"present": False}},
    )
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"
    assert r.json()["mode"] == "lite"


def test_ready_is_503_when_rag_on_but_index_missing(client, monkeypatch):
    """RAG bật mà index chưa có -> 503 kèm lý do, không trả 'ok' giả."""
    import app.services.rag_service as mod

    monkeypatch.setattr(
        mod.rag_service, "status",
        lambda: {"status": "index_not_ready", "enabled": True, "ready": False,
                 "embedder": "not_loaded", "embedding_model": "x",
                 "index": {"present": False}},
    )
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "not_ready"
    assert body["mode"] == "rag"
    assert body["checks"]["rag"]["status"] == "index_not_ready"


def test_ready_is_200_when_rag_ready(client, monkeypatch):
    import app.services.rag_service as mod

    monkeypatch.setattr(
        mod.rag_service, "status",
        lambda: {"status": "ok", "enabled": True, "ready": True,
                 "embedder": "loaded", "embedding_model": "x",
                 "index": {"present": True}},
    )
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


def test_health_still_plain_ok(client):
    """/health là liveness: vẫn ok dù RAG chưa sẵn sàng."""
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# -------------------------------------------------------------- admin guard

ADMIN_ENDPOINTS = [
    ("post", "/api/v1/rag/index"),
    ("get", "/api/v1/rag/status"),
    ("get", "/api/v1/rag/list"),
]


@pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS)
def test_admin_endpoints_blocked_without_admin_key_configured(client, method, path, monkeypatch):
    """ADMIN_API_KEY trống -> fail-closed 503, không mở cho mọi người."""
    from app.core.config import get_settings

    monkeypatch.setenv("ADMIN_API_KEY", "")
    get_settings.cache_clear()
    try:
        r = getattr(client, method)(path)
        assert r.status_code == 503, r.text
        assert "ADMIN_API_KEY" in r.json()["detail"]
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS)
def test_admin_endpoints_reject_wrong_key(client, method, path, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("ADMIN_API_KEY", "s3cret")
    get_settings.cache_clear()
    try:
        r = getattr(client, method)(path, headers={"X-Admin-Key": "wrong"})
        assert r.status_code == 403, r.text
        r2 = getattr(client, method)(path)          # thiếu header
        assert r2.status_code == 403
    finally:
        get_settings.cache_clear()


def test_rag_status_returns_payload_with_valid_key(client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("ADMIN_API_KEY", "s3cret")
    get_settings.cache_clear()
    try:
        r = client.get("/api/v1/rag/status", headers={"X-Admin-Key": "s3cret"})
        assert r.status_code == 200
        body = r.json()
        assert "status" in body and "index" in body and "embedding_model" in body
    finally:
        get_settings.cache_clear()


def test_rag_index_returns_409_when_already_running(client, monkeypatch):
    from app.core.config import get_settings
    import app.services.rag_service as mod

    monkeypatch.setenv("ADMIN_API_KEY", "s3cret")
    get_settings.cache_clear()

    def busy(*a, **k):
        raise RuntimeError("Đang có một tiến trình reindex khác chạy.")

    monkeypatch.setattr(mod.rag_service, "index_knowledge_base", busy)
    try:
        r = client.post("/api/v1/rag/index", headers={"X-Admin-Key": "s3cret"})
        assert r.status_code == 409
        assert "reindex" in r.json()["detail"]
    finally:
        get_settings.cache_clear()


def test_rag_index_reports_chunk_count(client, monkeypatch):
    from app.core.config import get_settings
    import app.services.rag_service as mod

    monkeypatch.setenv("ADMIN_API_KEY", "s3cret")
    get_settings.cache_clear()
    monkeypatch.setattr(mod.rag_service, "index_knowledge_base", lambda *a, **k: 42)
    try:
        r = client.post("/api/v1/rag/index", headers={"X-Admin-Key": "s3cret"})
        assert r.status_code == 200
        assert r.json()["indexed_chunks"] == 42
    finally:
        get_settings.cache_clear()


def test_rag_index_500_keeps_old_index_message(client, monkeypatch):
    from app.core.config import get_settings
    import app.services.rag_service as mod

    monkeypatch.setenv("ADMIN_API_KEY", "s3cret")
    get_settings.cache_clear()

    def boom(*a, **k):
        raise ValueError("disk full")

    monkeypatch.setattr(mod.rag_service, "index_knowledge_base", boom)
    try:
        r = client.post("/api/v1/rag/index", headers={"X-Admin-Key": "s3cret"})
        assert r.status_code == 500
        assert "index cũ" in r.json()["detail"]
    finally:
        get_settings.cache_clear()


# ------------------------------------------------------------- /rag/search

def test_search_distinguishes_no_evidence_from_outage(client, monkeypatch):
    """Không có bằng chứng -> 200 + status=no_evidence (hệ thống vẫn khỏe)."""
    import app.services.rag_service as mod

    monkeypatch.setattr(
        mod.rag_service, "retrieve_detailed",
        lambda q, k=3: RetrievalResult(RagStatus.NO_EVIDENCE, detail="không khớp"),
    )
    r = client.post("/api/v1/rag/search", params={"query": "xyz"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "no_evidence"
    assert body["num_results"] == 0


def test_search_returns_503_when_index_not_ready(client, monkeypatch):
    """Index chưa sẵn sàng là sự cố hạ tầng -> 503, không phải 200 rỗng."""
    import app.services.rag_service as mod

    monkeypatch.setattr(
        mod.rag_service, "retrieve_detailed",
        lambda q, k=3: RetrievalResult(RagStatus.INDEX_NOT_READY, detail="chưa index"),
    )
    r = client.post("/api/v1/rag/search", params={"query": "xyz"})
    assert r.status_code == 503
    assert r.json()["status"] == "index_not_ready"


def test_search_returns_503_on_retrieval_error(client, monkeypatch):
    import app.services.rag_service as mod

    monkeypatch.setattr(
        mod.rag_service, "retrieve_detailed",
        lambda q, k=3: RetrievalResult(RagStatus.RETRIEVAL_ERROR, detail="boom"),
    )
    r = client.post("/api/v1/rag/search", params={"query": "xyz"})
    assert r.status_code == 503
    assert r.json()["detail"] == "boom"


def test_search_returns_structured_sources_on_hit(client, monkeypatch):
    import app.services.rag_service as mod

    docs = [(
        FakeDoc(
            "The present perfect connects the past with the present moment.",
            {
                "source": "/kb/grammar.txt", "page": 2,
                "doc_id": "grammar.txt", "chunk_id": "grammar.txt#2:0",
                "section": "Tenses", "language": "en", "content_hash": "abc123def4567890",
            },
        ),
        0.3,
    )]
    monkeypatch.setattr(
        mod.rag_service, "retrieve_detailed",
        lambda q, k=3: RetrievalResult(
            RagStatus.OK, documents=docs, context="Present perfect..."
        ),
    )
    r = client.post("/api/v1/rag/search", params={"query": "present perfect"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["num_results"] == 1
    # Nguồn có cấu trúc: ID ổn định để gán nhãn eval + đoạn bằng chứng, chứ không
    # chỉ một đường dẫn tuyệt đối của máy build.
    src = body["sources"][0]
    assert src["doc_id"] == "grammar.txt"
    assert src["chunk_id"] == "grammar.txt#2:0"
    assert src["page"] == 2
    assert src["section"] == "Tenses"
    assert src["language"] == "en"
    assert src["content_hash"] == "abc123def4567890"
    assert src["score"] == 0.3
    assert "present perfect" in src["evidence"].lower()
    assert "index_version" in body


def test_search_sources_tolerate_legacy_chunks_without_metadata(client, monkeypatch):
    """Chunk của index cũ không có doc_id/chunk_id — API không được vỡ."""
    import app.services.rag_service as mod

    docs = [(FakeDoc("old chunk", {"source": "grammar.txt"}), None)]
    monkeypatch.setattr(
        mod.rag_service, "retrieve_detailed",
        lambda q, k=3: RetrievalResult(RagStatus.OK, documents=docs, context="old chunk"),
    )
    r = client.post("/api/v1/rag/search", params={"query": "x"})
    assert r.status_code == 200
    src = r.json()["sources"][0]
    assert src["doc_id"] is None and src["chunk_id"] is None
    assert src["source"] == "grammar.txt"
    assert src["evidence"] == "old chunk"


def test_search_returns_503_when_index_incompatible(client, monkeypatch):
    """Index build bằng model khác -> 503 + hướng dẫn reindex, không phải 200 rỗng."""
    import app.services.rag_service as mod

    monkeypatch.setattr(
        mod.rag_service, "retrieve_detailed",
        lambda q, k=3: RetrievalResult(
            RagStatus.INDEX_INCOMPATIBLE, detail="model cũ != model mới"
        ),
    )
    r = client.post("/api/v1/rag/search", params={"query": "x"})
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "index_incompatible"
    assert "/rag/index" in body["message"]
    assert body["detail"]


def test_ready_is_503_when_index_incompatible(client, monkeypatch):
    """Index có mặt nhưng không khớp model -> readiness phải đỏ, kèm lý do."""
    import app.services.rag_service as mod

    monkeypatch.setattr(
        mod.rag_service, "status",
        lambda: {"status": "index_incompatible", "enabled": True, "ready": False,
                 "embedder": "loaded", "embedding_model": "new-model",
                 "last_error": "",
                 "index": {"present": True, "version": "v1", "compatible": False,
                           "incompatible_reason": "build bằng model old-model"}},
    )
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 503
    check = r.json()["checks"]["rag"]
    assert check["index_present"] is True
    assert check["index_compatible"] is False
    assert "old-model" in check["reason"]
    assert check["index_version"] == "v1"


# -------------------------------------------------------------- /rag/rollback

def test_rollback_requires_admin(client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("ADMIN_API_KEY", "s3cret")
    get_settings.cache_clear()
    try:
        r = client.post("/api/v1/rag/rollback", json={"version": ""})
        assert r.status_code == 403
    finally:
        get_settings.cache_clear()


def test_rollback_returns_activated_version(client, monkeypatch):
    from app.core.config import get_settings
    import app.services.rag_service as mod

    monkeypatch.setenv("ADMIN_API_KEY", "s3cret")
    get_settings.cache_clear()
    monkeypatch.setattr(mod.rag_service, "rollback", lambda v="": "20260101-000000")
    try:
        r = client.post(
            "/api/v1/rag/rollback",
            json={"version": ""},
            headers={"X-Admin-Key": "s3cret"},
        )
        assert r.status_code == 200
        assert r.json()["active_version"] == "20260101-000000"
    finally:
        get_settings.cache_clear()


def test_rollback_409_when_no_previous_version(client, monkeypatch):
    from app.core.config import get_settings
    import app.services.rag_service as mod

    monkeypatch.setenv("ADMIN_API_KEY", "s3cret")
    get_settings.cache_clear()

    def no_candidate(v=""):
        raise RuntimeError("Không có version cũ nào để rollback.")

    monkeypatch.setattr(mod.rag_service, "rollback", no_candidate)
    try:
        r = client.post(
            "/api/v1/rag/rollback",
            json={"version": ""},
            headers={"X-Admin-Key": "s3cret"},
        )
        assert r.status_code == 409
        assert "rollback" in r.json()["detail"]
    finally:
        get_settings.cache_clear()
