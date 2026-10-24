"""Kiểm chứng end-to-end pipeline index/retrieval: ChromaDB THẬT, persistence THẬT.

Chạy:  PYTHONPATH=. python scripts/verify_rag_pipeline.py
Cần:   langchain-community, chromadb  (requirements.txt, không có ở lite)
Env:   VERIFY_TMP=<dir> thư mục làm việc (mặc định ./.rag-verify, bị xoá đầu mỗi lần chạy).

Kiểm chứng gì:

Embedder là hàm bag-of-words xác định (deterministic), KHÔNG phải model thật:
huggingface.co bị chặn egress trong môi trường chạy. Phần được kiểm chứng ở đây
là vectorstore/persistence/atomic swap — đúng phần code vừa sửa — chứ không phải
chất lượng của embedding model.
"""
import gc
import hashlib
import os
import shutil
import sys
from pathlib import Path

# Mặc định dùng thư mục trong repo, KHÔNG dùng /tmp: trên một số môi trường
# (overlayfs/tmpfs trong container) SQLite của ChromaDB ghi lặp lại ở /tmp sẽ lỗi
# "attempt to write a readonly database".
TMP = Path(os.environ.get("VERIFY_TMP") or ".rag-verify")
shutil.rmtree(TMP, ignore_errors=True)
KB = TMP / "kb"; KB.mkdir(parents=True)
(KB / "grammar.txt").write_text(
    "The present perfect tense is formed with have or has plus the past participle. "
    "It describes actions completed at an unspecified time.", encoding="utf-8")
(KB / "toeic.txt").write_text(
    "TOEIC Part 5 tests incomplete sentences with grammar and vocabulary. "
    "Each question has four answer options labelled A through D.", encoding="utf-8")

os.environ["RAG_ENABLED"] = "true"
os.environ["CHROMA_PERSIST_DIR"] = str(TMP / "vectorstore")
os.environ["VIENG_CACHE_DIR"] = str(TMP / "cache")
os.environ["RAG_KEEP_OLD_INDEXES"] = "1"

from app.core.config import get_settings
get_settings.cache_clear()
import app.services.rag_service as mod
from app.services.rag_service import RAGService, RagStatus

DIM = 256


class HashEmbeddings:
    """Bag-of-words hashing embedding — xác định, offline, đủ để test retrieval."""

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


svc = RAGService()
svc._get_embeddings = lambda: HashEmbeddings()
active = Path(svc._persist_dir)

print("== 1. Trước khi index ==")
st = svc.status()
print(f"  status={st['status']} ready={st['ready']}")
r = svc.retrieve_detailed("present perfect")
print(f"  retrieve_detailed -> {r.status.value}")
assert r.status is RagStatus.INDEX_NOT_READY

print("== 2. Index lần đầu (Chroma thật, ghi xuống đĩa) ==")
n = svc.index_knowledge_base(docs_dir=str(KB))
print(f"  chunks={n}")
assert n > 0
files = list(active.rglob("*"))
print(f"  file: {len(files)} | version={svc.active_version()}")
assert any(f.suffix == ".sqlite3" for f in files), "Chroma phải ghi sqlite thật"
assert (active / "CURRENT").exists(), "phải có con trỏ CURRENT"

st = svc.status()
print(f"  status={st['status']} ready={st['ready']} num_chunks={st['index']['num_chunks']}")
assert st["ready"] is True

r = svc.retrieve_detailed("present perfect tense formed with have or has", k=1)
print(f"  retrieve -> {r.status.value} | src={Path(r.documents[0][0].metadata.get('source','')).name}")
assert r.status is RagStatus.OK
assert "present perfect" in r.context.lower()

r2 = svc.retrieve_detailed("TOEIC Part 5 incomplete sentences answer options", k=1)
print(f"  retrieve(toeic) -> {r2.status.value} | src={Path(r2.documents[0][0].metadata.get('source','')).name}")
assert "toeic" in r2.context.lower()

print("== 3. Reindex thành công -> swap + giữ bản cũ ==")
(KB / "ielts.txt").write_text(
    "IELTS Writing Task 2 requires at least 250 words in academic essay style.",
    encoding="utf-8")
n2 = svc.index_knowledge_base(docs_dir=str(KB))
print(f"  chunks sau reindex={n2} (trước={n})")
assert n2 > n
vers = svc.list_versions()
print(f"  versions trên đĩa: {vers} | đang dùng: {svc.active_version()}")
assert len(vers) == 2, f"kỳ vọng 2 version (mới + cũ để rollback), có {vers}"
assert svc.active_version() == vers[0], "CURRENT phải trỏ bản mới nhất"
r3 = svc.retrieve_detailed("IELTS Writing Task 2 requires 250 words", k=3)
srcs3 = sorted(Path(d.metadata.get("source","")).name for d, _ in r3.documents)
print(f"  retrieve(ielts) -> {r3.status.value} docs={len(r3.documents)} srcs={srcs3}")
assert len(r3.documents) == 3, f"index mới phải có 3 chunk, truy xuất được {len(r3.documents)}"
assert "250 words" in r3.context, "index mới chưa có tài liệu mới (đang đọc index cũ?)"

print("== 4. Reindex LỖI -> index đang chạy phải còn nguyên ==")
orig = mod.RAGService._verify_staged
mod.RAGService._verify_staged = lambda self, store, expected: (_ for _ in ()).throw(
    RuntimeError("mô phỏng verify thất bại"))
try:
    svc.index_knowledge_base(docs_dir=str(KB))
    print("  !! SAI: đáng ra phải raise"); sys.exit(1)
except RuntimeError as e:
    print(f"  raise đúng: {e}")
finally:
    mod.RAGService._verify_staged = orig

vers_after = svc.list_versions()
print(f"  versions sau khi lỗi: {vers_after} | CURRENT={svc.active_version()}")
assert vers_after == vers, f"version chưa kích hoạt phải được dọn: {vers_after} vs {vers}"

svc.reset()
svc._get_embeddings = lambda: HashEmbeddings()
r4 = svc.retrieve_detailed("IELTS Writing Task 2 requires 250 words", k=3)
print(f"  index cũ vẫn dùng được -> {r4.status.value} docs={len(r4.documents)}")
assert r4.status is RagStatus.OK
assert "250 words" in r4.context, "INDEX ĐANG CHẠY BỊ MẤT sau reindex lỗi!"

print("== 5. Persistence qua 'restart' (service instance mới) ==")
# Mô phỏng restart: bỏ HẲN instance cũ (thả client + xoá reference) rồi mới tạo
# instance mới. Hai RAGService cùng sống và cùng mở một path trong một tiến trình
# là pattern của test, không phải của app (app chỉ có một rag_service singleton);
# chromadb dùng chung system nội bộ theo path nên đóng cái này khi cái kia còn
# sống sẽ làm hỏng state chung.
svc._release_vectorstore()
_old = svc
svc2 = RAGService()
del _old
gc.collect()
svc2._get_embeddings = lambda: HashEmbeddings()
st2 = svc2.status()
print(f"  instance mới: status={st2['status']} ready={st2['ready']}")
assert st2["ready"] is True, "index không sống sót qua restart"
r5 = svc2.retrieve_detailed("TOEIC Part 5 incomplete sentences", k=1)
print(f"  retrieve sau restart -> {r5.status.value} docs={len(r5.documents)}")
assert r5.status is RagStatus.OK

print("== 6. Chỉ giữ N version cũ (rag_keep_old_indexes=1) ==")
# svc (instance cũ) vẫn giữ client Chroma mở trên version đời đầu. Thả ra trước
# khi prune xoá version đó — hai service dùng chung một index là chuyện của test,
# không phải pattern của production (app chỉ có một rag_service).
svc2.index_knowledge_base(docs_dir=str(KB))
vs6 = svc2.list_versions()
print(f"  sau 3 lần index, versions: {vs6}")
assert len(vs6) == 2, f"prune sai, phải còn 2 (current + 1 cũ): {vs6}"

print("== 7. Rollback về version trước ==")
cur = svc2.active_version()
prev = [v for v in svc2.list_versions() if v != cur][0]
got = svc2.rollback()
svc2._get_embeddings = lambda: HashEmbeddings()
print(f"  {cur} -> {got} (kỳ vọng {prev})")
assert got == prev
assert svc2.active_version() == prev
r7 = svc2.retrieve_detailed("TOEIC Part 5 incomplete sentences", k=1)
print(f"  retrieve sau rollback -> {r7.status.value} docs={len(r7.documents)}")
assert r7.status is RagStatus.OK, "index sau rollback phải dùng được"

print("== 8. Reindex LỖI không được làm hỏng các lần reindex SAU ==")
# Hồi quy cho bug thật: xoá thư mục của một client Chroma còn sống phá trạng thái
# sqlite của cả tiến trình, khiến mọi lần reindex sau fail "readonly database".
orig = mod.RAGService._verify_staged
mod.RAGService._verify_staged = lambda self, store, expected: (_ for _ in ()).throw(
    RuntimeError("fail giả lần 2"))
try:
    svc2.index_knowledge_base(docs_dir=str(KB))
    print("  !! SAI: đáng ra phải raise"); sys.exit(1)
except RuntimeError as e:
    print(f"  build lỗi như mong đợi: {e}")
finally:
    mod.RAGService._verify_staged = orig

for attempt in (1, 2):
    n8 = svc2.index_knowledge_base(docs_dir=str(KB))
    print(f"  reindex sau lỗi, lần {attempt}: chunks={n8} ver={svc2.active_version()}")
    assert n8 > 0, "reindex sau một lần lỗi phải vẫn chạy được"
svc2.reset()
svc2._get_embeddings = lambda: HashEmbeddings()
r8 = svc2.retrieve_detailed("TOEIC Part 5 incomplete sentences", k=1)
print(f"  retrieve -> {r8.status.value}")
assert r8.status is RagStatus.OK

print("\nTẤT CẢ KIỂM CHỨNG E2E PASS")
