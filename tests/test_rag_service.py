"""Test RAGService: trạng thái tường minh + reindex an toàn.

Không cần model embedding thật hay API trả phí: dùng fake embedder/vectorstore
in-memory, nên chạy được trong CI.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from app.services.rag_service import (
    DEGRADED_STATUSES,
    RagStatus,
    RAGService,
    RetrievalResult,
)


class FakeDoc:
    def __init__(self, content: str, metadata: dict | None = None):
        self.page_content = content
        self.metadata = metadata or {}


class FakeCollection:
    def __init__(self, n: int):
        self._n = n

    def count(self):
        return self._n


class FakeStore:
    """Vectorstore giả: trả docs cố định, hoặc raise nếu được yêu cầu."""

    def __init__(self, docs=None, raises: Exception | None = None, count: int | None = None):
        self._docs = docs if docs is not None else []
        self._raises = raises
        self._collection = FakeCollection(count if count is not None else len(self._docs))

    def similarity_search(self, query, k=3):
        if self._raises:
            raise self._raises
        return self._docs[:k]

    def max_marginal_relevance_search(self, query, k=3, fetch_k=10, lambda_mult=0.7):
        if self._raises:
            raise self._raises
        return self._docs[:k]

    def similarity_search_with_score(self, query, k=5):
        if self._raises:
            raise self._raises
        return [(d, 0.5) for d in self._docs[:k]]


@pytest.fixture
def svc(tmp_path, monkeypatch):
    """RAGService trỏ vào tmp_path, RAG bật."""
    monkeypatch.setenv("RAG_ENABLED", "true")
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "vectorstore"))
    from app.core.config import get_settings

    get_settings.cache_clear()
    s = RAGService()
    yield s
    get_settings.cache_clear()


def _make_index(svc, marker: str = "old", version: str = "v-old") -> Path:
    """Tạo một version index giả và trỏ CURRENT vào nó."""
    p = svc._versions_root / version
    p.mkdir(parents=True, exist_ok=True)
    (p / "marker.txt").write_text(marker, encoding="utf-8")
    svc._write_current(version)
    return p


def _make_legacy_index(svc, marker: str = "legacy") -> Path:
    """Index theo layout cũ: ghi thẳng vào <root>, không có CURRENT."""
    p = Path(svc._persist_dir)
    p.mkdir(parents=True, exist_ok=True)
    (p / "chroma.sqlite3").write_text(marker, encoding="utf-8")
    return p


# --------------------------------------------------------------- trạng thái

def test_disabled_is_distinct_from_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("RAG_ENABLED", "false")
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "vs"))
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        s = RAGService()
        r = s.retrieve_detailed("hello")
        assert r.status is RagStatus.DISABLED
        assert r.context == ""
        assert s.retrieve("hello") == ""          # API cũ vẫn trả string rỗng
        assert s.status()["status"] == "disabled"
        assert s.is_ready() is False
    finally:
        get_settings.cache_clear()


def test_index_not_ready_when_no_vectorstore(svc):
    r = svc.retrieve_detailed("hello")
    assert r.status is RagStatus.INDEX_NOT_READY
    assert r.degraded is True
    assert "index" in r.detail.lower() or svc._persist_dir in r.detail
    assert svc.is_ready() is False


def test_embedder_unavailable_reported(svc):
    _make_index(svc)
    svc._embedder_broken = True
    svc._last_error = "embedder: OSError: model not found"
    r = svc.retrieve_detailed("hello")
    assert r.status is RagStatus.EMBEDDER_UNAVAILABLE
    assert "model not found" in r.detail
    assert svc.status()["status"] == "embedder_unavailable"


def test_no_evidence_is_not_degraded(svc, monkeypatch):
    _make_index(svc)
    monkeypatch.setattr(svc, "_get_vectorstore", lambda: FakeStore(docs=[]))
    r = svc.retrieve_detailed("hello")
    assert r.status is RagStatus.NO_EVIDENCE
    assert r.degraded is False                    # kho tài liệu không khớp != hệ thống lỗi
    assert r.status not in DEGRADED_STATUSES


def test_retrieval_error_distinct_from_no_evidence(svc, monkeypatch):
    _make_index(svc)
    monkeypatch.setattr(
        svc, "_get_vectorstore", lambda: FakeStore(raises=RuntimeError("chroma boom"))
    )
    r = svc.retrieve_detailed("hello")
    assert r.status is RagStatus.RETRIEVAL_ERROR
    assert r.degraded is True
    assert "chroma boom" in r.detail


def test_ok_returns_context_and_sources(svc, monkeypatch):
    _make_index(svc)
    docs = [
        FakeDoc("Present perfect is used for...", {"source": "grammar.txt", "page": 2}),
        FakeDoc("Past simple is used for...", {"source": "grammar.txt", "page": 3}),
    ]
    monkeypatch.setattr(svc, "_get_vectorstore", lambda: FakeStore(docs=docs))
    r = svc.retrieve_detailed("present perfect", k=2)
    assert r.status is RagStatus.OK
    assert r.ok is True
    assert len(r.documents) == 2
    assert "Present perfect" in r.context
    assert "grammar.txt" in r.context
    # API string cũ vẫn tương thích
    assert svc.retrieve("present perfect", k=2) == r.context


def test_mmr_and_scores_report_states(svc, monkeypatch):
    _make_index(svc)
    monkeypatch.setattr(
        svc, "_get_vectorstore", lambda: FakeStore(raises=RuntimeError("boom"))
    )
    assert svc.retrieve_mmr_detailed("q").status is RagStatus.RETRIEVAL_ERROR
    assert svc.retrieve_with_scores_detailed("q").status is RagStatus.RETRIEVAL_ERROR
    assert svc.retrieve_mmr("q") == ""            # API cũ vẫn string rỗng
    assert svc.retrieve_with_scores("q") == []


def test_scores_above_threshold_is_no_evidence(svc, monkeypatch):
    """Truy xuất được nhưng mọi chunk đều trên ngưỡng -> NO_EVIDENCE, không phải lỗi."""
    _make_index(svc)

    class HighScoreStore(FakeStore):
        def similarity_search_with_score(self, query, k=5):
            return [(FakeDoc("irrelevant"), 9.9)]

    monkeypatch.setattr(svc, "_get_vectorstore", lambda: HighScoreStore())
    r = svc.retrieve_with_scores_detailed("q")
    assert r.status is RagStatus.NO_EVIDENCE
    assert "ngưỡng" in r.detail
    assert r.degraded is False


def test_status_payload_shape(svc):
    _make_index(svc)
    st = svc.status()
    assert set(st) >= {"status", "enabled", "ready", "embedding_model", "embedder", "index"}
    assert st["index"]["present"] is True
    assert st["index"]["persist_dir"] == svc._persist_dir


def test_retrieval_result_as_dict():
    r = RetrievalResult(RagStatus.NO_EVIDENCE, detail="nope")
    d = r.as_dict()
    assert d["status"] == "no_evidence"
    assert d["num_documents"] == 0


# ------------------------------------------------------------------ reindex

def _install_fake_langchain(monkeypatch, *, build, chunks_out=None):
    """Cài module langchain giả để index_knowledge_base chạy được không cần deps thật.

    `build(documents, embedding, persist_directory)` quyết định thành công/thất bại.

    `from_documents` nhận `ids` và `**kwargs` giống Chroma thật; ID được ghi vào
    `captured_ids` để test kiểm tra index có dùng ID ổn định hay không.
    """
    captured: dict = {}
    vs_mod = types.ModuleType("langchain_community.vectorstores")

    class Chroma:
        @staticmethod
        def from_documents(documents, embedding, persist_directory, ids=None, **kwargs):
            captured["ids"] = ids
            captured["kwargs"] = kwargs
            return build(documents, embedding, persist_directory)

        def __init__(self, persist_directory=None, embedding_function=None, **kwargs):
            self._collection = FakeCollection(1)

    vs_mod.Chroma = Chroma

    split_mod = types.ModuleType("langchain_text_splitters")

    class RecursiveCharacterTextSplitter:
        def __init__(self, **kw):
            pass

        def split_documents(self, documents):
            return chunks_out if chunks_out is not None else documents

    split_mod.RecursiveCharacterTextSplitter = RecursiveCharacterTextSplitter

    loaders_mod = types.ModuleType("langchain_community.document_loaders")
    loaders_mod.DirectoryLoader = object
    loaders_mod.TextLoader = object
    core_docs = types.ModuleType("langchain_core.documents")
    core_docs.Document = FakeDoc

    for name, mod in [
        ("langchain_community.vectorstores", vs_mod),
        ("langchain_text_splitters", split_mod),
        ("langchain_community.document_loaders", loaders_mod),
        ("langchain_core.documents", core_docs),
    ]:
        monkeypatch.setitem(sys.modules, name, mod)

    return captured


@pytest.fixture
def kb(tmp_path):
    """Knowledge base giả có 1 file .txt."""
    d = tmp_path / "kb"
    d.mkdir()
    (d / "grammar.txt").write_text("Present perfect rules.", encoding="utf-8")
    return d


def test_reindex_keeps_old_index_when_build_fails(svc, kb, monkeypatch):
    """Build lỗi -> CURRENT không đổi, version chưa kích hoạt bị dọn."""
    active = _make_index(svc, marker="old")

    def boom(documents, embedding, persist_directory):
        raise RuntimeError("embedding service down")

    _install_fake_langchain(monkeypatch, build=boom, chunks_out=[FakeDoc("c1")])
    monkeypatch.setattr(svc, "_load_documents", lambda d: [FakeDoc("doc1")])
    monkeypatch.setattr(svc, "_get_embeddings", lambda: object())

    with pytest.raises(RuntimeError, match="embedding service down"):
        svc.index_knowledge_base(docs_dir=str(kb))

    assert svc.active_version() == "v-old"
    assert (active / "marker.txt").read_text(encoding="utf-8") == "old"
    assert svc.list_versions() == ["v-old"], "version lỗi phải được dọn"


def test_reindex_keeps_old_index_when_verify_fails(svc, kb, monkeypatch):
    """Build xong nhưng index rỗng -> không đổi CURRENT."""
    active = _make_index(svc, marker="old")

    def build_empty(documents, embedding, persist_directory):
        Path(persist_directory).mkdir(parents=True, exist_ok=True)
        return FakeStore(docs=[], count=0)         # count=0 -> verify fail

    _install_fake_langchain(monkeypatch, build=build_empty, chunks_out=[FakeDoc("c1")])
    monkeypatch.setattr(svc, "_load_documents", lambda d: [FakeDoc("doc1")])
    monkeypatch.setattr(svc, "_get_embeddings", lambda: object())

    with pytest.raises(RuntimeError, match="rỗng"):
        svc.index_knowledge_base(docs_dir=str(kb))

    assert svc.active_version() == "v-old"
    assert (active / "marker.txt").read_text(encoding="utf-8") == "old"


def test_reindex_fails_when_chunk_count_mismatch(svc, kb, monkeypatch):
    active = _make_index(svc, marker="old")

    def build_short(documents, embedding, persist_directory):
        Path(persist_directory).mkdir(parents=True, exist_ok=True)
        return FakeStore(docs=[FakeDoc("a")], count=1)   # kỳ vọng 2

    _install_fake_langchain(
        monkeypatch, build=build_short, chunks_out=[FakeDoc("c1"), FakeDoc("c2")]
    )
    monkeypatch.setattr(svc, "_load_documents", lambda d: [FakeDoc("doc1")])
    monkeypatch.setattr(svc, "_get_embeddings", lambda: object())

    with pytest.raises(RuntimeError, match="kỳ vọng 2"):
        svc.index_knowledge_base(docs_dir=str(kb))
    assert svc.active_version() == "v-old"
    assert (active / "marker.txt").read_text(encoding="utf-8") == "old"


def test_reindex_activates_new_version_on_success(svc, kb, monkeypatch):
    """Build + verify ok -> CURRENT trỏ version mới, version cũ vẫn trên đĩa."""
    _make_index(svc, marker="old")
    chunks = [FakeDoc("c1"), FakeDoc("c2")]

    def build_ok(documents, embedding, persist_directory):
        pd = Path(persist_directory)
        pd.mkdir(parents=True, exist_ok=True)
        (pd / "marker.txt").write_text("new", encoding="utf-8")
        return FakeStore(docs=[FakeDoc("a"), FakeDoc("b")], count=len(chunks))

    _install_fake_langchain(monkeypatch, build=build_ok, chunks_out=chunks)
    monkeypatch.setattr(svc, "_load_documents", lambda d: [FakeDoc("doc1")])
    monkeypatch.setattr(svc, "_get_embeddings", lambda: object())

    count = svc.index_knowledge_base(docs_dir=str(kb))

    assert count == 2
    new_version = svc.active_version()
    assert new_version != "v-old"
    active = svc.active_index_path()
    assert (active / "marker.txt").read_text(encoding="utf-8") == "new"
    assert "v-old" in svc.list_versions(), "phải giữ version cũ để rollback"


def test_reindex_never_renames_the_live_index_dir(svc, kb, monkeypatch):
    """Hồi quy: ChromaDB cache client theo path, nên không được rename thư mục
    index đang dùng — chỉ đổi con trỏ CURRENT."""
    old_active = _make_index(svc, marker="old")
    old_inode = old_active.stat().st_ino
    chunks = [FakeDoc("c1")]

    def build_ok(documents, embedding, persist_directory):
        Path(persist_directory).mkdir(parents=True, exist_ok=True)
        return FakeStore(docs=[FakeDoc("a")], count=1)

    _install_fake_langchain(monkeypatch, build=build_ok, chunks_out=chunks)
    monkeypatch.setattr(svc, "_load_documents", lambda d: [FakeDoc("doc1")])
    monkeypatch.setattr(svc, "_get_embeddings", lambda: object())

    svc.index_knowledge_base(docs_dir=str(kb))

    assert old_active.exists(), "thư mục version cũ phải còn nguyên tại chỗ"
    assert old_active.stat().st_ino == old_inode
    assert svc.active_index_path() != old_active


def test_prune_keeps_configured_number_of_old_versions(svc, kb, monkeypatch):
    for i in range(4):
        d = svc._versions_root / f"v{i}"
        d.mkdir(parents=True)
        (d / "x").write_text("x", encoding="utf-8")
    svc._write_current("v3")
    svc._keep_old = 1
    svc._prune_old_versions(keep_current="v3")
    assert sorted(svc.list_versions()) == ["v2", "v3"]


def test_rollback_to_previous_version(svc):
    for name in ("v1", "v2"):
        d = svc._versions_root / name
        d.mkdir(parents=True)
        (d / "x").write_text("x", encoding="utf-8")
    svc._write_current("v2")
    assert svc.rollback() == "v1"
    assert svc.active_version() == "v1"


def test_rollback_to_named_version(svc):
    for name in ("v1", "v2", "v3"):
        d = svc._versions_root / name
        d.mkdir(parents=True)
        (d / "x").write_text("x", encoding="utf-8")
    svc._write_current("v3")
    assert svc.rollback("v1") == "v1"
    assert svc.active_version() == "v1"


def test_rollback_rejects_unknown_version(svc):
    _make_index(svc)
    with pytest.raises(RuntimeError, match="Không có index version nope"):
        svc.rollback("nope")


def test_rollback_without_candidate_raises(svc):
    _make_index(svc)
    with pytest.raises(RuntimeError, match="rollback"):
        svc.rollback()


def test_legacy_layout_still_usable(svc):
    """Index theo layout cũ (ghi thẳng vào root) vẫn dùng được, không cần reindex."""
    legacy = _make_legacy_index(svc)
    assert svc.active_index_path() == legacy
    assert svc.active_version() == "legacy"
    assert svc.is_ready() is True


def test_current_pointer_to_missing_version_is_not_ready(svc):
    """CURRENT trỏ vào version đã bị xoá -> coi như chưa có index, không crash."""
    svc._write_current("ghost")
    assert svc.active_index_path() is None
    assert svc.retrieve_detailed("q").status is RagStatus.INDEX_NOT_READY


def test_reindex_without_documents_keeps_old_index(svc, tmp_path, monkeypatch):
    """Thư mục knowledge base rỗng -> trả 0, không đổi index đang chạy."""
    active = _make_index(svc, marker="old")
    empty = tmp_path / "empty_kb"
    empty.mkdir()
    assert svc.index_knowledge_base(docs_dir=str(empty)) == 0
    assert svc.active_version() == "v-old"
    assert (active / "marker.txt").read_text(encoding="utf-8") == "old"


def test_reindex_rejects_concurrent_run(svc, kb, monkeypatch):
    """Lần reindex thứ hai khi lock đang giữ -> RuntimeError, không build chồng."""
    svc._index_lock.acquire()
    try:
        with pytest.raises(RuntimeError, match="reindex khác"):
            svc.index_knowledge_base(docs_dir=str(kb))
    finally:
        svc._index_lock.release()


def test_reindex_raises_when_embedder_unavailable(svc, kb, monkeypatch):
    _make_index(svc, marker="old")
    _install_fake_langchain(monkeypatch, build=lambda *a, **k: None, chunks_out=[FakeDoc("c")])
    monkeypatch.setattr(svc, "_load_documents", lambda d: [FakeDoc("doc1")])
    monkeypatch.setattr(svc, "_get_embeddings", lambda: None)

    with pytest.raises(RuntimeError, match="Embedder không khả dụng"):
        svc.index_knowledge_base(docs_dir=str(kb))
    assert svc.active_version() == "v-old"


def test_reindex_reports_missing_rag_stack_clearly(svc, kb, monkeypatch):
    """Chế độ lite (không có langchain) -> lỗi nói rõ, không phải ModuleNotFoundError."""
    _make_index(svc, marker="old")
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name.startswith("langchain"):
            raise ImportError(f"No module named {name!r}")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(RuntimeError, match="Stack RAG chưa được cài"):
        svc.index_knowledge_base(docs_dir=str(kb))


def test_reset_clears_broken_flags(svc):
    svc._embedder_broken = True
    svc._vectorstore_broken = True
    svc._last_error = "x"
    svc.reset()
    assert svc._embedder_broken is False
    assert svc._vectorstore_broken is False
    assert svc._last_error == ""


# ---------------------------------------------- dọn version lỗi (an toàn tiến trình)

def test_failed_build_leaves_incomplete_marker_not_deleted_in_process(svc, kb, monkeypatch):
    """Build lỗi -> thư mục version còn lại kèm .incomplete, KHÔNG bị rmtree ngay.

    Hồi quy cho bug thật: rmtree thư mục của một client Chroma còn sống phá trạng
    thái sqlite của cả tiến trình, khiến MỌI lần reindex sau đó fail với
    "attempt to write a readonly database".
    """
    _make_index(svc, marker="old")

    def build_then_fail(documents, embedding, persist_directory):
        Path(persist_directory).mkdir(parents=True, exist_ok=True)
        return FakeStore(docs=[], count=0)      # verify fail

    _install_fake_langchain(monkeypatch, build=build_then_fail, chunks_out=[FakeDoc("c")])
    monkeypatch.setattr(svc, "_load_documents", lambda d: [FakeDoc("d")])
    monkeypatch.setattr(svc, "_get_embeddings", lambda: object())

    with pytest.raises(RuntimeError):
        svc.index_knowledge_base(docs_dir=str(kb))

    leftovers = [
        d for d in svc._versions_root.iterdir()
        if (d / ".incomplete").exists()
    ]
    assert len(leftovers) == 1, "version lỗi phải còn lại kèm marker"
    # và không được tính là version dùng được
    assert svc.list_versions() == ["v-old"]
    assert svc.active_version() == "v-old"


def test_incomplete_version_from_this_process_is_not_cleaned(svc):
    """_cleanup_incomplete bỏ qua version lỗi do chính tiến trình này tạo."""
    d = svc._versions_root / "v-broken"
    d.mkdir(parents=True)
    (d / ".incomplete").write_text("building", encoding="utf-8")   # mtime = bây giờ
    svc._cleanup_incomplete()
    assert d.exists(), "không được xoá trong cùng tiến trình"


def test_stale_incomplete_version_is_cleaned(svc):
    """Version lỗi từ lần chạy TRƯỚC (mtime cũ hơn process start) thì được dọn."""
    import os

    import app.services.rag_service as mod

    d = svc._versions_root / "v-stale"
    d.mkdir(parents=True)
    marker = d / ".incomplete"
    marker.write_text("building", encoding="utf-8")
    old = mod._PROCESS_START - 3600
    os.utime(marker, (old, old))

    svc._cleanup_incomplete()
    assert not d.exists(), "version lỗi cũ phải được dọn"


def test_successful_build_removes_incomplete_marker(svc, kb, monkeypatch):
    _make_index(svc, marker="old")
    chunks = [FakeDoc("c1")]

    def build_ok(documents, embedding, persist_directory):
        pd = Path(persist_directory)
        pd.mkdir(parents=True, exist_ok=True)
        (pd / "chroma.sqlite3").write_text("data", encoding="utf-8")
        return FakeStore(docs=[FakeDoc("a")], count=1)

    _install_fake_langchain(monkeypatch, build=build_ok, chunks_out=chunks)
    monkeypatch.setattr(svc, "_load_documents", lambda d: [FakeDoc("d")])
    monkeypatch.setattr(svc, "_get_embeddings", lambda: object())

    svc.index_knowledge_base(docs_dir=str(kb))
    active = svc.active_index_path()
    assert active is not None
    assert not (active / ".incomplete").exists()
    assert svc.active_version() in svc.list_versions()


# =====================================================================
# Tương thích index: embedding model / distance metric / schema metadata
# =====================================================================
#
# Bug được chặn ở đây: đổi EMBEDDING_MODEL mà không reindex. Vector trong index
# thuộc không gian của model cũ, nên truy vấn vẫn "chạy" và trả về kết quả vô
# nghĩa — hoặc Chroma báo một lỗi dimension rất khó hiểu. Cả hai đều âm thầm.


def _write_meta(svc, version: str, **fields) -> Path:
    """Tạo version index giả kèm index_meta.json."""
    from app.services.rag_metadata import write_index_meta

    p = _make_index(svc, version=version)
    meta = {"embedding_model": svc._embedding_model, "distance_metric": ""}
    meta.update(fields)
    write_index_meta(p, meta)
    return p


def test_index_meta_is_empty_without_index(svc):
    assert svc.index_meta() == {}
    assert svc.index_compatibility_problem() == ""


def test_index_meta_is_read_from_active_version(svc):
    _write_meta(svc, "v1", num_chunks=42)
    assert svc.index_meta()["num_chunks"] == 42


def test_compatible_index_has_no_problem(svc):
    _write_meta(svc, "v1")
    assert svc.index_compatibility_problem() == ""
    assert svc.status()["index"]["compatible"] is True


def test_model_mismatch_blocks_vectorstore_load(svc, monkeypatch):
    """Index build bằng model khác -> KHÔNG mở index, báo INDEX_INCOMPATIBLE."""
    _write_meta(svc, "v1", embedding_model="some-other-model")
    # Embedder "ổn" để chứng minh việc chặn đến từ metadata, không phải lỗi embedder.
    monkeypatch.setattr(svc, "_get_embeddings", lambda: object())

    assert svc._get_vectorstore() is None
    assert svc._index_incompatible
    result = svc.retrieve_detailed("present perfect")
    assert result.status is RagStatus.INDEX_INCOMPATIBLE
    assert result.degraded, "phải là trạng thái degraded, không phải 'không có kết quả'"
    assert "some-other-model" in result.detail
    assert svc._embedding_model in result.detail


def test_model_mismatch_shows_in_status_and_is_not_ready(svc):
    _write_meta(svc, "v1", embedding_model="some-other-model")
    st = svc.status()
    assert st["status"] == RagStatus.INDEX_INCOMPATIBLE.value
    assert st["ready"] is False
    assert st["index"]["present"] is True, "index vẫn có trên đĩa"
    assert st["index"]["compatible"] is False
    assert "/rag/index" in st["index"]["incompatible_reason"]
    assert svc.is_ready() is False


def test_distance_metric_mismatch_is_detected(svc, monkeypatch):
    monkeypatch.setattr(svc, "_distance_metric", "cosine")
    _write_meta(svc, "v1", distance_metric="l2")
    assert "distance metric" in svc.index_compatibility_problem()


def test_legacy_index_without_meta_still_loads(svc, monkeypatch):
    """Index của bản cũ không có index_meta.json — không được chặn."""
    _make_index(svc, version="v-old")
    monkeypatch.setattr(svc, "_get_embeddings", lambda: object())
    assert svc.index_meta() == {}
    assert svc.index_compatibility_problem() == ""
    assert svc.status()["index"]["compatible"] is True


def test_dimension_mismatch_error_maps_to_incompatible(svc, monkeypatch):
    """Lỗi dimension của Chroma là 'phải reindex', không phải 'thử lại sau'."""
    err = ValueError(
        "Collection expecting embedding with dimension of 384, got 1024"
    )
    monkeypatch.setattr(svc, "_resolve_store", lambda: (FakeStore(raises=err), None))

    for call in (
        svc.retrieve_detailed,
        svc.retrieve_mmr_detailed,
        svc.retrieve_with_scores_detailed,
    ):
        result = call("query")
        assert result.status is RagStatus.INDEX_INCOMPATIBLE, call.__name__
        assert "reindex" in result.detail.lower() or "/rag/index" in result.detail


def test_unrelated_retrieval_error_stays_retrieval_error(svc, monkeypatch):
    err = RuntimeError("attempt to write a readonly database")
    monkeypatch.setattr(svc, "_resolve_store", lambda: (FakeStore(raises=err), None))
    assert svc.retrieve_detailed("q").status is RagStatus.RETRIEVAL_ERROR


def test_reset_clears_incompatible_flag(svc):
    svc._index_incompatible = "stale"
    svc.reset()
    assert svc._index_incompatible == ""


def test_collection_kwargs_empty_by_default(svc):
    """Mặc định KHÔNG ghi hnsw:space — giữ nguyên hành vi (và SCORE_THRESHOLD)."""
    assert svc._collection_kwargs() == {}


def test_collection_kwargs_set_when_metric_configured(svc, monkeypatch):
    monkeypatch.setattr(svc, "_distance_metric", "cosine")
    assert svc._collection_kwargs() == {
        "collection_metadata": {"hnsw:space": "cosine"}
    }


def test_embedding_dim_reads_from_embedder(svc):
    class E:
        def embed_query(self, text):
            return [0.0] * 768

    assert svc._embedding_dim(E()) == 768


def test_embedding_dim_returns_none_on_error(svc):
    class E:
        def embed_query(self, text):
            raise RuntimeError("model not downloaded")

    assert svc._embedding_dim(E()) is None


def test_status_falls_back_to_meta_chunk_count(svc):
    """num_chunks lấy từ metadata khi vectorstore chưa được load."""
    _write_meta(svc, "v1", num_chunks=123)
    assert svc._vectorstore is None
    assert svc.status()["index"]["num_chunks"] == 123


# =====================================================================
# Indexing ghi ID ổn định + index_meta.json
# =====================================================================


def test_reindex_passes_stable_ids_to_chroma(svc, kb, monkeypatch):
    """Không truyền `ids` thì Chroma tự cấp UUID -> mỗi lần index một tập ID khác."""
    chunks = [
        FakeDoc("Present perfect", {"source": str(kb / "a.txt")}),
        FakeDoc("Past simple", {"source": str(kb / "a.txt")}),
    ]
    captured = _install_fake_langchain(
        monkeypatch, build=lambda d, e, p: FakeStore(docs=d, count=len(d)),
        chunks_out=chunks,
    )
    monkeypatch.setattr(svc, "_load_documents", lambda d: [FakeDoc("doc1")])
    monkeypatch.setattr(svc, "_get_embeddings", lambda: object())

    assert svc.index_knowledge_base(docs_dir=str(kb)) == 2
    assert captured["ids"] == ["a.txt#0:0", "a.txt#0:1"]
    assert len(set(captured["ids"])) == 2


def test_reindex_writes_index_meta(svc, kb, monkeypatch):
    class Emb:
        def embed_query(self, text):
            return [0.1] * 384

    chunks = [FakeDoc("Present perfect", {"source": str(kb / "a.txt")})]
    _install_fake_langchain(
        monkeypatch, build=lambda d, e, p: FakeStore(docs=d, count=len(d)),
        chunks_out=chunks,
    )
    monkeypatch.setattr(svc, "_load_documents",
                        lambda d: [FakeDoc("doc1", {"source": str(kb / "a.txt")})])
    monkeypatch.setattr(svc, "_get_embeddings", lambda: Emb())

    svc.index_knowledge_base(docs_dir=str(kb))

    meta = svc.index_meta()
    assert meta["embedding_model"] == svc._embedding_model
    assert meta["embedding_dim"] == 384
    assert meta["num_chunks"] == 1
    assert meta["version"] == svc.active_version()
    assert meta["chunk_size"] and meta["chunk_overlap"]
    # Phiên bản corpus: hai lần đo chỉ so sánh được khi fingerprint giống nhau.
    assert len(meta["corpus_fingerprint"]) == 16
    assert meta["created_at"].endswith("Z")
    # Index vừa build phải tự tương thích với cấu hình đang chạy.
    assert svc.index_compatibility_problem() == ""


def test_index_meta_absent_when_build_fails(svc, kb, monkeypatch):
    """Build lỗi -> không được ghi metadata cho version lỗi, và version cũ giữ nguyên."""
    from app.services.rag_metadata import INDEX_META_FILE

    active = _make_index(svc, version="v-old")
    _install_fake_langchain(
        monkeypatch,
        build=lambda d, e, p: (_ for _ in ()).throw(RuntimeError("embedding down")),
        chunks_out=[FakeDoc("c1", {"source": str(kb / "a.txt")})],
    )
    monkeypatch.setattr(svc, "_load_documents", lambda d: [FakeDoc("doc1")])
    monkeypatch.setattr(svc, "_get_embeddings", lambda: object())

    with pytest.raises(RuntimeError, match="embedding down"):
        svc.index_knowledge_base(docs_dir=str(kb))

    assert svc.active_version() == "v-old"
    assert not (active / INDEX_META_FILE).exists()


def test_reindex_metadata_lands_on_chunks(svc, kb, monkeypatch):
    """Chunk đi vào Chroma phải mang đủ doc_id/chunk_id/content_hash."""
    chunks = [FakeDoc(
        "## Tenses\nThe present perfect is used for actions that are not finished.",
        {"source": str(kb / "g/a.txt")},
    )]
    _install_fake_langchain(
        monkeypatch, build=lambda d, e, p: FakeStore(docs=d, count=len(d)),
        chunks_out=chunks,
    )
    monkeypatch.setattr(svc, "_load_documents", lambda d: [FakeDoc("doc1")])
    monkeypatch.setattr(svc, "_get_embeddings", lambda: object())

    svc.index_knowledge_base(docs_dir=str(kb))

    m = chunks[0].metadata
    assert m["doc_id"] == "g/a.txt"
    assert m["chunk_id"] == "g/a.txt#0:0"
    assert m["section"] == "Tenses"
    assert m["language"] == "en"
    assert len(m["content_hash"]) == 16
    assert m["version"] == svc.active_version()
