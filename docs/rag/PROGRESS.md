# ViEng RAG — tiến độ

Nhánh phát triển: `automation/vieng-rag`. File này là trạng thái dùng chung giữa
các lần chạy — đọc trước khi chọn việc, cập nhật trước khi commit.

Quy ước trạng thái: `TODO` · `IN_PROGRESS` · `DONE` · `BLOCKED`.
Một hạng mục chỉ `DONE` khi có **implementation + bằng chứng kiểm chứng + tài liệu**.

---

## Lần chạy 2026-10-24 (#1)

Điểm bắt đầu: `main` @ `cd454d0`. Chưa có `docs/rag/`, chưa có nhánh automation.
Baseline test trước khi sửa: **39 passed**.

### Đã làm

**P0-1 — Chuẩn hoá cache/temp, bỏ đường dẫn ổ đĩa cố định — DONE**

- Thêm `app/core/paths.py`: gốc cache lấy từ `CACHE_DIR` / `VIENG_CACHE_DIR`, mặc
  định `./data/cache`; các thư mục con (`ocr/temp`, `paddle`, `huggingface`) đều
  override riêng được bằng env. `ensure_dir()` fallback sang temp của OS khi gốc
  cache không ghi được (vd. volume read-only) thay vì làm sập request.
- `app/services/ocr_service.py`: bỏ 5 chỗ hard-code `E:\AI_CACHE\paddle_ocr\...`
  (`TEMP`, `TMP`, `PADDLE_PDX_CACHE_HOME`, 2 chỗ `NamedTemporaryFile(dir=...)`).
  Trước đó OCR chỉ chạy được trên đúng một máy Windows; trên Linux/Docker thì
  `os.makedirs('E:\\...')` tạo một thư mục tên lạ ngay trong workdir.
- `EMBEDDING_MODEL`: mặc định cũ `sentence-transformers/models--BAAI--bge-m3` là
  **tên thư mục cache HF**, không phải repo id → không resolve được. Đổi thành
  `BAAI/bge-m3`. `.env.example` cũng đang ghi `E:/AI_CACHE/sentence_transformers/...`
  → đã sửa.
- Có test hồi quy quét toàn bộ `app/**.py` để chặn đường dẫn ổ đĩa quay lại.

**P0-2 — Phân biệt lite / RAG, kiểm tra khởi động và readiness — DONE**

- `rag_service.status()` trả trạng thái tổng hợp: enabled, embedder
  (`not_loaded|loaded|broken`), index (present, version, available_versions,
  num_chunks), `last_error`.
- `GET /api/v1/health/ready`: `RAG_ENABLED=false` → 200 `mode=lite` (app chạy
  bình thường, chỉ không có RAG). RAG bật nhưng embedder/index chưa sẵn sàng →
  **503** kèm lý do, thay vì "ok" giả rồi mọi câu trả lời đều thiếu căn cứ.
  `/health` giữ nguyên là liveness.
- `GET /api/v1/rag/status` (quản trị): trạng thái chi tiết.
- Startup log rõ `status / embedder / index_present / model`.
- Index lần đầu chuyển sang **chạy nền** (`asyncio.create_task` +
  `run_in_threadpool`). Trước đây build embedding block cả lifespan, nên readiness
  probe không bao giờ xanh và k8s sẽ kill pod trước khi index xong.

**P0-3 — Phân biệt các lý do không có context — DONE**

- `RagStatus`: `OK` · `DISABLED` · `EMBEDDER_UNAVAILABLE` · `INDEX_NOT_READY` ·
  `RETRIEVAL_ERROR` · `NO_EVIDENCE`; `DEGRADED_STATUSES` tách "hệ thống hỏng"
  khỏi "kho tài liệu không có gì khớp".
- `RetrievalResult(status, documents, context, detail)` + `retrieve_detailed()`,
  `retrieve_mmr_detailed()`, `retrieve_with_scores_detailed()`.
- Các API string cũ (`retrieve`, `retrieve_mmr`, `retrieve_with_scores`,
  `retrieve_for_topic`) **giữ nguyên chữ ký** → caller hiện tại không phải sửa.
- `POST /rag/search` trả `status` + `detail` + `sources` có cấu trúc; trạng thái
  degraded trả 503 chứ không phải 200 rỗng.
- Reindex ở chế độ lite (không có langchain) báo lỗi rõ ràng thay vì để
  `ModuleNotFoundError` lọt lên API — lỗi này do test phát hiện: hàm cũ import
  stack nặng *trước* khi kiểm tra có tài liệu hay không.

**P0-4 — Reindex an toàn, có version và rollback — DONE**

Hàm cũ `shutil.rmtree(persist_dir)` **trước khi** build bản mới → build lỗi là
mất luôn index đang chạy. Nay:

- Layout: `<root>/CURRENT` (con trỏ text) + `<root>/versions/<ver>/`.
- Build vào version mới → verify (đúng số chunk + một truy vấn thật) → chỉ khi
  verify xong mới `os.replace` con trỏ `CURRENT`. Index đang chạy không bị chạm.
- **Không rename thư mục index đang dùng.** ChromaDB cache client theo *đường
  dẫn*; rename thư mục bên dưới nó làm handle cũ trỏ vào inode cũ và truy vấn trả
  **dữ liệu cũ**. Bản đầu của patch này dùng rename-swap và đã bị bug đó — test
  e2e bắt được (unit test với fake store không thấy).
- `rollback(version="")` + `POST /rag/rollback`: quay về version trước.
- `rag_keep_old_indexes` (mặc định 1) quyết định giữ bao nhiêu version cũ.
- Lock chống reindex chạy chồng → `409`.
- Marker `.incomplete`: xem "Bug đã sửa" bên dưới.

**P0-5 (một phần) — Lời gọi đồng bộ nặng trong endpoint async — DONE cho RAG**

- `POST /rag/index`, `POST /rag/search`, `POST /rag/rollback` chạy qua
  `run_in_threadpool`. Index lần đầu ở startup chạy nền.
- *Chưa làm:* giới hạn concurrency cho embedding/OCR (`rag_max_concurrency` đã
  thêm vào config nhưng **chưa được dùng**) — xem backlog.

**P0-7 — Quyền quản trị cho thao tác index / xem kho tài liệu — DONE**

- Header `X-Admin-Key` so với `ADMIN_API_KEY`, dùng `secrets.compare_digest`.
- **Fail-closed**: `ADMIN_API_KEY` trống → 503, endpoint bị chặn hoàn toàn (không
  phải mở cho mọi người).
- Áp cho `POST /rag/index`, `GET /rag/status`, `GET /rag/list`, `POST /rag/rollback`.
- Trước đó `POST /rag/index` không có auth: bất kỳ ai cũng xoá được index.

### Bug thật đã sửa trong lúc làm (cả hai do test e2e phát hiện)

1. **Rename-swap trả dữ liệu cũ.** ChromaDB cache client theo đường dẫn, nên đổi
   tên thư mục index đang dùng khiến truy vấn sau đó đọc index cũ. Sửa bằng layout
   version + con trỏ `CURRENT` (không rename gì cả). Test hồi quy:
   `test_reindex_never_renames_the_live_index_dir`.
2. **Một lần reindex lỗi làm hỏng mọi lần reindex sau.** `shutil.rmtree` thư mục
   của một client Chroma **còn sống** (traceback của exception đang bay vẫn giữ
   frame) phá trạng thái sqlite của *cả tiến trình*; mọi lần index sau đó fail
   `attempt to write a readonly database` cho tới khi restart app. Sửa bằng:
   - marker `.incomplete` trong version đang build, xoá sau khi verify xong;
     `list_versions()` / `active_index_path()` bỏ qua version có marker;
   - **không** rmtree ở nhánh lỗi; dọn ở đầu lần reindex sau, và chỉ dọn version
     có marker **cũ hơn thời điểm tiến trình này bắt đầu** (`_PROCESS_START`) —
     version lỗi do chính tiến trình này tạo thì để sau khi restart mới dọn;
   - `_verify_staged` bỏ reference tới store trước khi raise.
   Bằng chứng: trước khi sửa, reindex #2 sau một lần lỗi fail ngay; sau khi sửa,
   reindex #2..#5 đều chạy. Test: 4 test trong `tests/test_rag_service.py` +
   bước 8 của `scripts/verify_rag_pipeline.py`.

Cũng đã tránh một bug tự gây: `_release_vectorstore` ban đầu gọi `client.reset()`
để "đóng kết nối" — trong ChromaDB đó là lệnh **xoá sạch dữ liệu**, sẽ làm rỗng
index ngay trước khi giữ lại làm bản rollback.

### Kiểm thử đã chạy

| Hạng mục | Kết quả |
|---|---|
| `pytest -q` (`RAG_ENABLED=false`, lite) | **102 passed** (baseline 39 → +63 test mới) |
| `pytest -q` (`RAG_ENABLED=true`) | 102 passed |
| `pyflakes` trên file đã sửa/thêm | sạch |
| `python -c "import app.main"` | ok |
| `scripts/verify_rag_pipeline.py` (ChromaDB thật) | **8/8 bước PASS**, chạy lại 3 lần đều pass |

File test mới: `tests/test_rag_service.py` (31), `tests/test_rag_api.py` (21),
`tests/test_paths.py` (11).

`scripts/verify_rag_pipeline.py` kiểm chứng end-to-end với ChromaDB **thật** và
persistence **thật**: index lần đầu → truy xuất đúng tài liệu → reindex swap →
reindex lỗi giữ nguyên index cũ → sống sót qua "restart" → prune đúng số version
→ rollback → reindex lỗi không làm hỏng lần sau.

### Phần CHƯA xác minh / điểm cần lưu ý

- **Embedding model thật chưa chạy được ở đây**: `huggingface.co` bị chặn egress
  (403 ở proxy), nên không tải được `BAAI/bge-m3` hay cả MiniLM. Verify script
  dùng embedder bag-of-words xác định (offline) — nó kiểm chứng
  vectorstore/persistence/swap, **không** kiểm chứng chất lượng embedding. Cần
  chạy `scripts/verify_rag_pipeline.py` một lần trên máy có mạng HF, và phải tự
  xác nhận `BAAI/bge-m3` tải + embed được (mặc định mới chưa được chạy thật).
- **`chroma_persist_dir` đổi layout.** Index cũ (ghi thẳng vào root) vẫn dùng được
  nhờ nhánh legacy (`test_legacy_layout_still_usable`), và sẽ chuyển sang layout
  version ở lần reindex tới. Chưa kiểm chứng trên dữ liệu thật của ai.
- **ChromaDB nhiều client cùng một path trong một tiến trình**: đóng client này
  khi client kia còn sống làm hỏng state chung của chromadb. App chỉ có một
  `rag_service` singleton nên không gặp; nhưng đừng tạo `RAGService` thứ hai.
  `requirements.txt` để `chromadb>=0.5.18` (không pin) — môi trường test resolve
  ra **1.5.9**. Nên pin lại.
- **`/tmp` trong container này không chạy được ChromaDB** (`readonly database`
  khi ghi lặp); verify script mặc định dùng `./.rag-verify`.
- `status()["index"]["num_chunks"]` là `None` khi vectorstore chưa được load
  (ngay sau reindex) — đúng thiết kế, nhưng nếu muốn số liệu luôn có thì phải đọc
  từ đĩa.
- Chưa chạy được `paddleocr`/`paddlepaddle` ở đây (không có bản cho Python 3.13;
  CI dùng 3.11) → **phần OCR của P0-1 chưa chạy thật**, chỉ kiểm chứng bằng test
  đường dẫn. Cần xác nhận trên môi trường có Paddle.
- Chưa chạy `evals/` (cần `OPENROUTER_API_KEY`).

---

## Backlog

### P0 — Ổn định nền tảng
- [DONE] Chuẩn hoá cache/temp cross-platform, bỏ đường dẫn ổ đĩa cố định.
- [DONE] Phân biệt lite / RAG; kiểm tra khởi động + readiness theo embedding/index.
- [DONE] Phân biệt RAG tắt / index chưa sẵn sàng / không có bằng chứng / lỗi truy xuất.
- [DONE] Reindex: build version mới, verify, rồi chuyển; giữ bản cũ khi lỗi (+ rollback).
- [IN_PROGRESS] Lời gọi đồng bộ nặng trong endpoint async: RAG xong. **Còn lại:**
  dùng `rag_max_concurrency` để giới hạn concurrency embedding/OCR (hiện chỉ là
  config chưa dùng); rà các endpoint chat/OCR còn gọi sync.
- [TODO] Kiểm tra persistence của vectorstore khi restart/recreate container hoặc
  Pod. Đã kiểm chứng ở mức tiến trình (bước 5 verify script); **chưa** kiểm chứng
  với Docker/K8s volume thật — cần xem `k8s/` có mount PVC cho
  `CHROMA_PERSIST_DIR` không, và `docker-compose.yml` có volume không.
- [DONE] Quyền quản trị cho thao tác index và xem kho tài liệu.
- [TODO] Pin `chromadb` trong `requirements.txt` (hiện `>=0.5.18`, resolve ra 1.5.9)
  và cân nhắc chuyển sang `langchain-chroma` (bản `langchain_community.Chroma` đã
  deprecated). Cả hai đều chạy được ở đây.

### P1 — Đo chất lượng RAG (chưa bắt đầu — ưu tiên cho lần chạy sau)
- [TODO] Evaluation chạy qua retrieval thật, tách khỏi các suite eval LLM đang có
  (`evals/suites.py` hiện chỉ đo kiến thức LLM, không chạm vectorstore).
- [TODO] Định dạng dataset: `query_id`, `query`, nhãn `doc_id`/`chunk_id`, mức liên quan.
- [TODO] Hit Rate@K, Recall@K, MRR@K, NDCG@K + test công thức và trường hợp biên.
- [TODO] Tách tập dev/test; ghi phiên bản corpus, index (đã có `index.version`), cấu hình.
- [TODO] Đánh giá câu trả lời: đúng kiến thức, có căn cứ trong context, trích nguồn
  đúng, xử lý thiếu thông tin.
- [TODO] Đo latency từng bước và toàn luồng, báo p50/p95 (đã có `obs_stats` để dùng lại).
- [TODO] CI kiểm tra pipeline RAG bằng corpus nhỏ tái lập được, không cần API trả phí.
  Gợi ý: dùng embedder xác định như trong `scripts/verify_rag_pipeline.py` để CI
  lite cũng chạy được.

### P2 — Cải thiện retrieval (chưa bắt đầu)
- [TODO] Chuẩn hoá metadata và ID ổn định: `doc_id`, `chunk_id`, `source`, `page`,
  `section`, `language`, `version`, `content_hash`. Hiện chunk chỉ có `source` +
  `page` (PDF). **Nên làm trước P1** vì eval cần nhãn `doc_id`/`chunk_id` ổn định.
- [TODO] Kiểm tra tương thích embedding model / dimension / distance metric khi mở
  index. Hiện đổi `EMBEDDING_MODEL` mà không reindex sẽ lỗi hoặc cho kết quả rác.
  Nên ghi model + dim vào metadata của version và so khi load.
- [TODO] Chunking theo cấu trúc tài liệu (hiện `RecursiveCharacterTextSplitter`
  500/50 cho mọi loại), giữ quy tắc cùng ví dụ, bảo toàn bảng, kiểm soát theo token.
- [TODO] So sánh dense / MMR / hybrid BM25+dense hợp nhất bằng RRF (cần P1 trước
  để có đối chứng).
- [TODO] Cross-Encoder sau interface bật/tắt được; thử `BAAI/bge-reranker-v2-m3`.
- [TODO] Rerank tập ứng viên trước khi chọn context cuối, loại trùng, giới hạn token budget.

### P3 — Hoàn thiện trải nghiệm (chưa bắt đầu)
- [TODO] Trả nguồn có cấu trúc với document, page, `chunk_id`, đoạn bằng chứng.
  `/rag/search` đã trả `sources` (source + page) — còn `chunk_id` và đoạn bằng chứng.
- [TODO] Phân biệt tài liệu được truy xuất với nguồn thực sự hỗ trợ câu trả lời.
- [TODO] Truy vấn nối tiếp bằng lịch sử / query rewriting, tránh gọi thêm LLM mỗi lượt.
- [TODO] `conversation_id`, giới hạn lịch sử theo token budget, phân tách hội thoại.
- [TODO] Lưu PDF upload với `document_id` + phạm vi truy cập để lượt sau còn truy xuất được.
- [TODO] Ingestion dài → job nền có trạng thái, retry, checkpoint, chống trùng.
- [TODO] Mở rộng tracing cho parsing, embedding, retrieval, rerank, context, generation.
- [TODO] Load test, giới hạn tài nguyên, cache có khoá gắn với index version + phạm vi truy cập.

---

## Việc ưu tiên cho lần chạy sau

1. **P2 metadata + ID ổn định** (`doc_id`, `chunk_id`, `content_hash`, model/dim
   ghi vào version metadata). Làm trước P1 vì eval cần nhãn ổn định, và việc kiểm
   tra tương thích model/dim cũng dựa vào đây.
2. **P1 khung đo retrieval**: dataset format + Hit Rate/Recall/MRR/NDCG@K kèm test
   công thức, chạy được bằng embedder xác định để vào được CI lite.
3. Dọn phần còn lại của P0-5 (dùng `rag_max_concurrency`) và pin `chromadb`.
4. Kiểm chứng persistence với volume Docker/K8s thật (`k8s/`, `docker-compose.yml`).

## Tham chiếu

- `scripts/verify_rag_pipeline.py` — kiểm chứng e2e (cần `requirements.txt`, không
  chạy ở lite). `PYTHONPATH=. python scripts/verify_rag_pipeline.py`
- `app/core/paths.py` — mọi quyết định về cache/temp dir.
- `app/services/rag_service.py` — `RagStatus`, `RetrievalResult`, layout version.
- Endpoint quản trị cần header `X-Admin-Key` = `ADMIN_API_KEY`.
