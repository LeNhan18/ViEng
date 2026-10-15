"""RAG hybrid (BM25 + vector + RRF), rerank, endpoints index/list — không cần model embedding."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.services import rag_service as rs

rag = rs.rag_service

CORPUS = [
    ("since + mốc thời gian (since 2015); for + khoảng thời gian (for three years)", "grammar_since_for.txt"),
    ("Câu điều kiện loại 3: If + had + V3, would have + V3", "conditionals.txt"),
    ("Despite + danh từ / V-ing; although + mệnh đề", "connectors.txt"),
    ("Thì hiện tại hoàn thành dùng với since và for", "tenses.txt"),
]


class FakeCollection:
    def __init__(self, docs):
        self.docs = docs

    def get(self, include=None, limit=None, offset=None):
        items = self.docs[offset or 0:][: limit or None] if limit else self.docs[offset or 0:]
        return {"documents": [d for d, _ in items], "metadatas": [{"source": s} for _, s in items]}

    def count(self):
        return len(self.docs)


class FakeVectorStore:
    """Vector search giả: trả theo thứ tự cố định (mô phỏng embedding 'hiểu nghĩa' nhưng sai từ khoá)."""

    def __init__(self, docs, order):
        self._collection = FakeCollection(docs)
        self._docs = docs
        self._order = order

    def similarity_search(self, query, k=4):
        from langchain_core.documents import Document

        return [Document(page_content=self._docs[i][0], metadata={"source": self._docs[i][1]})
                for i in self._order[:k]]


@pytest.fixture
def store(monkeypatch):
    pytest.importorskip("langchain_core")
    pytest.importorskip("rank_bm25")
    vs = FakeVectorStore(CORPUS, order=[1, 2, 3, 0])  # vector xếp tài liệu đúng (0) cuối cùng
    monkeypatch.setattr(rag, "_enabled", True)
    monkeypatch.setattr(rag, "_get_vectorstore", lambda: vs)
    monkeypatch.setattr(rag, "_bm25", None)
    monkeypatch.setattr(rag, "_bm25_docs", [])
    monkeypatch.setattr(rag, "_bm25_unavailable", False)
    return vs


def test_tokenize_keeps_vietnamese():
    assert rs.tokenize("Thì hiện tại, since 2015!") == ["thì", "hiện", "tại", "since", "2015"]


def test_rrf_prefers_items_ranked_high_in_both():
    fused = rs.rrf_fuse([["a", "b", "c"], ["b", "c", "a"]])
    assert fused[0] == "b"
    assert set(fused) == {"a", "b", "c"}


def test_hybrid_rescues_keyword_match(store):
    # Vector search đặt tài liệu since/for xuống cuối; BM25 kéo nó lên nhờ từ khoá chính xác.
    docs = rag.hybrid_search("since for 2015", k=2, fetch_k=4)
    assert docs[0].metadata["source"] == "grammar_since_for.txt"
    vector_only = store.similarity_search("since for 2015", k=2)
    assert all(d.metadata["source"] != "grammar_since_for.txt" for d in vector_only)


def test_retrieve_formats_sources(store):
    ctx = rag.retrieve_mmr("since for", k=2)
    assert ctx.startswith("[Nguồn: ")
    assert "grammar_since_for.txt" in ctx


def test_reranker_reorders(store, monkeypatch):
    class FakeCE:
        def predict(self, pairs):
            return [10.0 if "Despite" in doc else 0.0 for _, doc in pairs]

    monkeypatch.setattr(rag, "_get_reranker", lambda: FakeCE())
    docs = rag.hybrid_search("since for", k=1, fetch_k=4)
    assert docs[0].metadata["source"] == "connectors.txt"


def test_hybrid_off_uses_vector_only(store, monkeypatch):
    monkeypatch.setenv("RAG_HYBRID", "false")
    get_settings.cache_clear()
    try:
        calls = []
        store.max_marginal_relevance_search = lambda q, k, fetch_k, lambda_mult: calls.append(q) or []
        rag.retrieve_mmr("since for", k=2)
        assert calls == ["since for"]
    finally:
        get_settings.cache_clear()


# ---------------- endpoints ----------------
def test_rag_list_is_paged(store):
    with TestClient(app) as c:
        r = c.get("/api/v1/rag/list?limit=2&offset=1").json()
    assert r["total"] == 4
    assert [ch["index"] for ch in r["chunks"]] == [2, 3]
    assert r["chunks"][0]["source"] == "conditionals.txt"


def test_rag_index_background_and_guard(monkeypatch):
    import time

    started = []
    monkeypatch.setattr(rag, "index_knowledge_base", lambda: started.append(1) or 7)
    monkeypatch.setenv("ADMIN_TOKEN", "secret")
    get_settings.cache_clear()
    try:
        with TestClient(app) as c:
            assert c.post("/api/v1/rag/index").status_code == 403
            r = c.post("/api/v1/rag/index", headers={"X-Admin-Token": "secret"})
            assert r.status_code == 202
            for _ in range(50):
                st = c.get("/api/v1/rag/index/status").json()
                if st["status"] == "done":
                    break
                time.sleep(0.05)
        assert st["status"] == "done" and st["chunks"] == 7 and started == [1]
    finally:
        get_settings.cache_clear()


def test_rag_index_blocked_in_production_without_token(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ADMIN_TOKEN", "")
    get_settings.cache_clear()
    try:
        with TestClient(app) as c:
            assert c.post("/api/v1/rag/index").status_code == 403
    finally:
        get_settings.cache_clear()
