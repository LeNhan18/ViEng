"""Test metadata và ID ổn định cho chunk (app/services/rag_metadata.py).

Chạy được ở chế độ lite: module không import langchain, các "chunk" ở đây là
object duck-typed có ``page_content`` + ``metadata`` giống Document.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest

from app.services import rag_metadata as rm


@dataclass
class FakeChunk:
    page_content: str
    metadata: dict = field(default_factory=dict)


# ------------------------------------------------------------------- content_hash


def test_content_hash_is_stable_and_whitespace_insensitive():
    a = rm.content_hash("Band 7 descriptors for writing")
    b = rm.content_hash("Band 7   descriptors\nfor writing\n")
    assert a == b, "format khác nhau nhưng cùng nội dung phải cùng hash"
    assert len(a) == 16
    assert a != rm.content_hash("Band 8 descriptors for writing")


def test_content_hash_handles_empty():
    assert rm.content_hash("") == rm.content_hash("   \n ")


# --------------------------------------------------------------------- doc_id_for


@pytest.mark.parametrize(
    "source, root, expected",
    [
        # Windows: separator "\" phải thành "/" để nhãn eval dùng được trên cả Linux.
        (r"E:\AI_CACHE\kb\ielts\band.txt", r"E:\AI_CACHE\kb", "ielts/band.txt"),
        ("/app/data/knowledge_base/toeic/part5.txt", "/app/data/knowledge_base",
         "toeic/part5.txt"),
        # root tương đối + source tuyệt đối: khớp theo hậu tố.
        ("/srv/app/data/knowledge_base/a/b.txt", "data/knowledge_base", "a/b.txt"),
        # source nằm ngoài root -> dùng tên file, không raise.
        ("/elsewhere/x.pdf", "data/knowledge_base", "x.pdf"),
        ("", "data/knowledge_base", "unknown"),
    ],
)
def test_doc_id_for(source, root, expected):
    assert rm.doc_id_for(source, root) == expected


def test_doc_id_is_identical_across_operating_systems():
    """Hồi quy cho lý do tồn tại của doc_id: đường dẫn tuyệt đối không ổn định."""
    win = rm.doc_id_for(r"C:\vieng\data\knowledge_base\g\tenses.txt",
                        r"C:\vieng\data\knowledge_base")
    linux = rm.doc_id_for("/opt/vieng/data/knowledge_base/g/tenses.txt",
                          "/opt/vieng/data/knowledge_base")
    assert win == linux == "g/tenses.txt"


# ------------------------------------------------------------- language / section


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Hướng dẫn luyện thi IELTS", "vi"),
        ("The candidate uses a range of structures", "en"),
        ("", "unknown"),
        ("12345 !!!", "unknown"),
        # Tiếng Việt không dấu: rơi về đếm từ chức năng.
        ("cac ban hoc sinh", "unknown"),
    ],
)
def test_detect_language(text, expected):
    assert rm.detect_language(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("## Writing Task 2\nBody text here", "Writing Task 2"),
        ("2.3 Coherence and Cohesion\nnội dung", "2.3 Coherence and Cohesion"),
        ("BAND DESCRIPTORS\nsomething", "BAND DESCRIPTORS"),
        ("just a normal sentence that is not a heading at all", ""),
        ("", ""),
    ],
)
def test_detect_section(text, expected):
    assert rm.detect_section(text) == expected


def test_detect_section_ignores_overly_long_lines():
    long_caps = "A" * 200
    assert rm.detect_section(f"{long_caps}\nbody") == ""


# ------------------------------------------------------------------ enrich_chunks


def _chunks():
    return [
        FakeChunk("## Tenses\nPresent perfect is used for...",
                  {"source": "/kb/grammar/tenses.txt"}),
        FakeChunk("Past simple describes finished actions.",
                  {"source": "/kb/grammar/tenses.txt"}),
        FakeChunk("Band 7 content", {"source": "/kb/ielts/band.pdf", "page": 3}),
    ]


def test_enrich_chunks_assigns_full_metadata_set():
    chunks = _chunks()
    ids = rm.enrich_chunks(chunks, docs_root="/kb", version="v1")
    assert ids == [
        "grammar/tenses.txt#0:0",
        "grammar/tenses.txt#0:1",
        "ielts/band.pdf#3:0",
    ]
    m = chunks[0].metadata
    for key in ("doc_id", "chunk_id", "content_hash", "language", "section",
                "version", "source", "metadata_schema"):
        assert key in m, f"thiếu {key}"
    assert m["doc_id"] == "grammar/tenses.txt"
    assert m["section"] == "Tenses"
    assert m["language"] == "en"
    assert m["version"] == "v1"
    assert chunks[2].metadata["page"] == 3


def test_enrich_chunks_is_deterministic():
    """Hai lần index cùng corpus phải cho cùng tập ID — nếu không, nhãn eval vô dụng."""
    first = rm.enrich_chunks(_chunks(), docs_root="/kb", version="v1")
    second = rm.enrich_chunks(_chunks(), docs_root="/kb", version="v2")
    assert first == second


def test_enrich_chunks_ids_are_unique_even_on_collision():
    """Chroma từ chối ID trùng; va chạm phải được tách ở đây."""
    dup = [
        FakeChunk("a", {"source": "/kb/x.txt", "page": 1}),
        FakeChunk("a", {"source": "/kb/x.txt", "page": 1}),
    ]
    ids = rm.enrich_chunks(dup, docs_root="/kb")
    assert len(set(ids)) == len(ids) == 2


def test_enrich_chunks_drops_none_values_for_chroma():
    """Chroma không nhận metadata value None."""
    chunks = [FakeChunk("x", {"source": "/kb/x.txt"})]
    rm.enrich_chunks(chunks, docs_root="/kb")
    assert all(v is not None for v in chunks[0].metadata.values())


def test_enrich_chunks_survives_non_numeric_page():
    chunks = [FakeChunk("x", {"source": "/kb/x.txt", "page": "intro"})]
    ids = rm.enrich_chunks(chunks, docs_root="/kb")
    assert ids == ["x.txt#intro:0"]


def test_enrich_chunks_without_version_omits_it():
    chunks = [FakeChunk("x", {"source": "/kb/x.txt"})]
    rm.enrich_chunks(chunks, docs_root="/kb")
    assert "version" not in chunks[0].metadata


# ------------------------------------------------------------ corpus_fingerprint


def test_corpus_fingerprint_is_order_independent():
    a, b = _chunks(), _chunks()
    rm.enrich_chunks(a, docs_root="/kb")
    rm.enrich_chunks(b, docs_root="/kb")
    b.reverse()
    assert rm.corpus_fingerprint(a) == rm.corpus_fingerprint(b)


def test_corpus_fingerprint_changes_with_content():
    a = _chunks()
    rm.enrich_chunks(a, docs_root="/kb")
    before = rm.corpus_fingerprint(a)
    b = _chunks()
    b[1].page_content = "Past simple describes something else entirely."
    rm.enrich_chunks(b, docs_root="/kb")
    assert rm.corpus_fingerprint(b) != before


def test_corpus_fingerprint_empty_corpus():
    assert rm.corpus_fingerprint([]) == rm.corpus_fingerprint([])


# -------------------------------------------------------------- evidence_snippet


def test_evidence_snippet_centers_on_query_term():
    body = ("intro " * 60) + "cohesion devices are used accurately " + ("tail " * 60)
    snip = rm.evidence_snippet(body, query="cohesion devices", max_len=120)
    assert "cohesion devices" in snip
    assert len(snip) <= 122  # +2 cho hai dấu "…"
    assert snip.startswith("…")


def test_evidence_snippet_short_text_returned_whole():
    assert rm.evidence_snippet("short text", query="anything") == "short text"


def test_evidence_snippet_without_match_takes_head():
    body = "a" * 500
    snip = rm.evidence_snippet(body, query="zzzz", max_len=100)
    assert snip.endswith("…")
    assert not snip.startswith("…")


def test_evidence_snippet_empty():
    assert rm.evidence_snippet("", query="x") == ""


# ------------------------------------------------------------------- index meta


def test_write_then_read_index_meta(tmp_path):
    meta = {"embedding_model": "BAAI/bge-m3", "num_chunks": 7}
    rm.write_index_meta(tmp_path, meta)
    assert (tmp_path / rm.INDEX_META_FILE).exists()
    assert rm.read_index_meta(tmp_path) == meta


def test_write_index_meta_leaves_no_temp_file(tmp_path):
    rm.write_index_meta(tmp_path, {"a": 1})
    assert [p.name for p in tmp_path.iterdir()] == [rm.INDEX_META_FILE]


def test_read_index_meta_missing_or_corrupt(tmp_path):
    assert rm.read_index_meta(tmp_path) == {}
    (tmp_path / rm.INDEX_META_FILE).write_text("{not json", encoding="utf-8")
    assert rm.read_index_meta(tmp_path) == {}


def test_index_meta_is_utf8_json_with_vietnamese(tmp_path):
    rm.write_index_meta(tmp_path, {"docs_dir": "dữ liệu/kho"})
    raw = (tmp_path / rm.INDEX_META_FILE).read_text(encoding="utf-8")
    assert "dữ liệu/kho" in raw
    assert json.loads(raw)["docs_dir"] == "dữ liệu/kho"


# --------------------------------------------------------- compatibility_problem


def test_no_problem_when_model_matches():
    meta = {"embedding_model": "BAAI/bge-m3", "distance_metric": ""}
    assert rm.compatibility_problem(meta, "BAAI/bge-m3", "") == ""


def test_model_mismatch_is_reported_with_both_names():
    meta = {"embedding_model": "BAAI/bge-m3"}
    problem = rm.compatibility_problem(meta, "all-MiniLM-L6-v2", "")
    assert "BAAI/bge-m3" in problem and "all-MiniLM-L6-v2" in problem
    assert "/rag/index" in problem, "phải nói rõ việc cần làm là reindex"


def test_distance_metric_mismatch_is_reported():
    meta = {"embedding_model": "m", "distance_metric": "l2"}
    assert "distance metric" in rm.compatibility_problem(meta, "m", "cosine")


def test_newer_metadata_schema_is_refused():
    meta = {"embedding_model": "m", "metadata_schema": rm.METADATA_SCHEMA_VERSION + 1}
    assert "schema" in rm.compatibility_problem(meta, "m", "")


def test_legacy_index_without_meta_is_not_blocked():
    """Index build bởi bản cũ không có metadata — không kết luận, cho dùng tiếp."""
    assert rm.compatibility_problem({}, "BAAI/bge-m3", "cosine") == ""


def test_meta_without_model_field_is_not_blocked():
    assert rm.compatibility_problem({"num_chunks": 3}, "BAAI/bge-m3", "") == ""


# ------------------------------------------------- looks_like_dimension_mismatch


@pytest.mark.parametrize("msg", [
    "Collection expecting embedding with dimension of 384, got 1024",
    "InvalidDimensionException: Embedding dimension 768 does not match "
    "collection dimensionality 384",
    "dimension mismatch",
])
def test_dimension_mismatch_detected(msg):
    assert rm.looks_like_dimension_mismatch(ValueError(msg))


@pytest.mark.parametrize("msg", [
    "attempt to write a readonly database",
    "connection refused",
    "no such table: collections",
])
def test_other_errors_are_not_dimension_mismatch(msg):
    assert not rm.looks_like_dimension_mismatch(RuntimeError(msg))
