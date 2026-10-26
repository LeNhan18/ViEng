"""Kiểm chứng end-to-end ID/metadata ổn định và kiểm tra tương thích index.

Chạy:  PYTHONPATH=. python scripts/verify_rag_metadata.py
Cần:   langchain-community, chromadb  (requirements.txt, không có ở lite)
Env:   VERIFY_TMP=<dir> thư mục làm việc (mặc định ./.rag-verify-meta).

Kiểm chứng gì (với ChromaDB THẬT, ghi xuống đĩa THẬT):

- Chunk đi vào index mang ID của *ta* (``doc_id``/``chunk_id``), không phải UUID
  do Chroma tự cấp — điều kiện cần để gán nhãn cho một bộ eval retrieval.
- Index cùng một corpus hai lần cho ra cùng tập ID và cùng ``corpus_fingerprint``.
- Thêm tài liệu mới không làm đổi ID của các chunk cũ.
- Đổi ``EMBEDDING_MODEL`` mà không reindex thì index bị **từ chối** kèm lý do, chứ
  không âm thầm trả kết quả vô nghĩa.

Tách khỏi ``verify_rag_pipeline.py`` có chủ đích: chromadb 1.x chia sẻ trạng thái
theo tiến trình, nên một tiến trình mở quá nhiều client (và rmtree thư mục của
client cũ) sẽ gặp lỗi "attempt to write a readonly database" ở một bước bất kỳ.
Mỗi script giữ số client trong một tiến trình ở mức an toàn.

Embedder là hàm bag-of-words xác định (offline): phần được kiểm chứng ở đây là ID,
metadata và kiểm tra tương thích, không phải chất lượng embedding model.
"""
import gc
import hashlib
import os
import shutil
import sys
from pathlib import Path

TMP = Path(os.environ.get("VERIFY_TMP") or ".rag-verify-meta")
shutil.rmtree(TMP, ignore_errors=True)
if TMP.exists():
    sys.exit(f"Không dọn được thư mục làm việc {TMP}. Xoá tay rồi chạy lại.")
KB = TMP / "kb"; KB.mkdir(parents=True)
(KB / "grammar.txt").write_text(
    "The present perfect tense is formed with have or has plus the past participle. "
    "It describes actions completed at an unspecified time.", encoding="utf-8")
(KB / "toeic.txt").write_text(
    "TOEIC Part 5 tests incomplete sentences with grammar and vocabulary. "
    "Each question has four answer options labelled A through D.", encoding="utf-8")
(KB / "ielts.txt").write_text(
    "IELTS Writing Task 2 requires at least 250 words in academic essay style.",
    encoding="utf-8")

os.environ["RAG_ENABLED"] = "true"
os.environ["CHROMA_PERSIST_DIR"] = str(TMP / "vectorstore")
os.environ["VIENG_CACHE_DIR"] = str(TMP / "cache")
os.environ["RAG_KEEP_OLD_INDEXES"] = "1"

from app.core.config import get_settings
get_settings.cache_clear()
from app.services.rag_service import RAGService, RagStatus

DIM = 256


class HashEmbeddings:
    """Bag-of-words hashing embedding — xác định, offline."""

    def _one(self, text: str):
        vec = [0.0] * DIM
        for tok in text.lower().split():
            tok = tok.strip(".,?!()")
            if not tok:
                continue
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16) % DIM
            vec[h] += 1.0
        norm = sum(v * v for v in vec) ** 0.5 or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts):
        return [self._one(t) for t in texts]

    def embed_query(self, text):
        return self._one(text)


svc2 = RAGService()
svc2._get_embeddings = lambda: HashEmbeddings()

print("== 0. Index lần đầu ==")
n = svc2.index_knowledge_base(docs_dir=str(KB))
print(f"  chunks={n} version={svc2.active_version()}")
assert n == 3, f"kỳ vọng 3 chunk từ 3 file, có {n}"

print("== 1. ID và metadata ổn định (Chroma thật) ==")
# Chroma tự cấp UUID khi không truyền `ids`, nên hai lần index cùng corpus sẽ cho
# hai tập ID khác nhau -> không gán nhãn eval được. Kiểm chứng ID là ID của ta.
svc2.reset()
svc2._get_embeddings = lambda: HashEmbeddings()
store = svc2._get_vectorstore()
raw = store._collection.get(include=["metadatas"])
ids_first = sorted(raw["ids"])
print(f"  {len(ids_first)} id, ví dụ: {ids_first[:3]}")
assert all("#" in i and ":" in i for i in ids_first), f"ID không theo schema: {ids_first[:3]}"
assert all(not i.count("-") >= 4 for i in ids_first), "vẫn là UUID do Chroma cấp"

metas = {m["chunk_id"]: m for m in raw["metadatas"]}
sample = metas[ids_first[0]]
print("  metadata mẫu:", {k: sample[k] for k in sorted(sample)})
for key in ("doc_id", "chunk_id", "content_hash", "language", "version", "source"):
    assert key in sample, f"thiếu metadata {key}"
assert not Path(sample["doc_id"]).is_absolute(), "doc_id phải là đường dẫn tương đối"
assert sample["doc_id"] in ("grammar.txt", "toeic.txt", "ielts.txt"), sample["doc_id"]
assert len(sample["content_hash"]) == 16

meta_file = svc2.index_meta()
print(f"  index_meta: model={meta_file['embedding_model']} dim={meta_file['embedding_dim']} "
      f"chunks={meta_file['num_chunks']} corpus={meta_file['corpus_fingerprint']}")
assert meta_file["embedding_dim"] == DIM
assert meta_file["num_chunks"] == len(ids_first)
assert meta_file["version"] == svc2.active_version()
fingerprint_before = meta_file["corpus_fingerprint"]

print("== 2. Reindex cùng corpus -> ID và fingerprint KHÔNG đổi ==")
# Thả client đang mở TRƯỚC khi reindex: prune sẽ rmtree một version cũ, và xoá
# thư mục khi còn client Chroma sống trong cùng tiến trình phá trạng thái sqlite
# của cả tiến trình (xem chú thích bước 5/6). App không gặp vì chỉ có một
# rag_service singleton và nó tự reset sau reindex.
svc2._release_vectorstore()
gc.collect()
svc2.index_knowledge_base(docs_dir=str(KB))
svc2.reset()
svc2._get_embeddings = lambda: HashEmbeddings()
store = svc2._get_vectorstore()
ids_second = sorted(store._collection.get()["ids"])
print(f"  ids giống nhau: {ids_second == ids_first}")
assert ids_second == ids_first, "ID phải ổn định giữa hai lần index cùng corpus"
assert svc2.index_meta()["corpus_fingerprint"] == fingerprint_before
assert svc2.index_meta()["version"] != meta_file["version"], "version index vẫn phải mới"

print("== 3. Corpus đổi -> fingerprint đổi, ID cũ vẫn giữ nguyên ==")
(KB / "extra.txt").write_text(
    "Phrasal verbs combine a verb with a particle to change the meaning.",
    encoding="utf-8")
svc2._release_vectorstore()
gc.collect()
svc2.index_knowledge_base(docs_dir=str(KB))
svc2.reset()
svc2._get_embeddings = lambda: HashEmbeddings()
meta_after = svc2.index_meta()
ids_third = set(svc2._get_vectorstore()._collection.get()["ids"])
print(f"  fingerprint {fingerprint_before} -> {meta_after['corpus_fingerprint']}")
assert meta_after["corpus_fingerprint"] != fingerprint_before
assert set(ids_first) <= ids_third, "chunk cũ không được đổi ID khi thêm tài liệu mới"
assert any(i.startswith("extra.txt#") for i in ids_third)

print("== 4. Đổi embedding model mà không reindex -> bị TỪ CHỐI ==")
# Bug âm thầm được chặn ở đây: vector trong index thuộc không gian model cũ, nên
# truy vấn vẫn "chạy" và trả kết quả vô nghĩa.
svc2._release_vectorstore()
svc3 = RAGService()
svc3._embedding_model = "một-model-hoàn-toàn-khác"
svc3._get_embeddings = lambda: HashEmbeddings()
problem = svc3.index_compatibility_problem()
print(f"  phát hiện: {problem[:90]}...")
assert problem, "phải phát hiện index build bằng model khác"
assert svc3._get_vectorstore() is None, "không được mở index không tương thích"
r12 = svc3.retrieve_detailed("TOEIC Part 5", k=1)
print(f"  retrieve -> {r12.status.value} (ready={svc3.status()['ready']})")
assert r12.status is RagStatus.INDEX_INCOMPATIBLE
assert r12.degraded
st12 = svc3.status()
assert st12["status"] == RagStatus.INDEX_INCOMPATIBLE.value
assert st12["index"]["present"] is True and st12["index"]["compatible"] is False
assert svc3.is_ready() is False

print("== 5. Trả model về đúng -> dùng lại được ngay, không cần reindex ==")
svc3 = RAGService()
svc3._get_embeddings = lambda: HashEmbeddings()
r13 = svc3.retrieve_detailed("TOEIC Part 5 incomplete sentences", k=1)
print(f"  retrieve -> {r13.status.value} chunk_id={r13.documents[0][0].metadata.get('chunk_id')}")
assert r13.status is RagStatus.OK
assert r13.documents[0][0].metadata.get("chunk_id"), "chunk truy xuất phải mang chunk_id"


print("\nTẤT CẢ KIỂM CHỨNG ID/METADATA PASS")
