# Metadata và ID ổn định của chunk

Tài liệu này mô tả metadata mà mỗi chunk trong vectorstore mang theo, cách ID
được sinh, và cơ chế kiểm tra tương thích index. Đây là nền cho bộ đánh giá
retrieval (cần nhãn `doc_id`/`chunk_id` ổn định) và cho việc trả nguồn có cấu
trúc ở API.

Code: `app/services/rag_metadata.py`. Kiểm chứng:
`scripts/verify_rag_metadata.py` (ChromaDB thật), `tests/test_rag_metadata.py`.

## Vì sao cần

Trước đây một chunk chỉ có `source` (đường dẫn **tuyệt đối** trên máy build) và
`page` nếu là PDF. Hai hệ quả:

1. **Không gán nhãn eval được.** `E:\AI_CACHE\kb\a.txt` và
   `/app/data/knowledge_base/a.txt` là cùng một tài liệu nhưng khác chuỗi, nên
   không dùng làm nhãn; chunk thì không có ID nào cả.
2. **Reindex sinh ID mới hoàn toàn.** Không truyền `ids` thì Chroma tự cấp UUID,
   nên hai lần index cùng một corpus cho ra hai tập ID khác nhau — không so sánh
   được giữa các version index.

## Các field

| Field | Ví dụ | Ghi chú |
|---|---|---|
| `doc_id` | `grammar/tenses.txt` | Đường dẫn **POSIX tương đối** so với gốc corpus. Giống nhau trên Windows, Ubuntu và Docker. |
| `chunk_id` | `grammar/tenses.txt#0:2` | `<doc_id>#<page>:<ordinal>`. Duy nhất trong một index; ổn định giữa các lần index cùng nội dung. |
| `chunk_ordinal` | `2` | Thứ tự chunk trong cùng (doc, page). |
| `content_hash` | `877c14db5373b9a7` | sha256 (16 hex đầu) của nội dung đã chuẩn hoá khoảng trắng. Đổi format không đổi hash. |
| `source` | `/app/data/knowledge_base/grammar/tenses.txt` | Giữ nguyên như trước để không phá caller cũ. |
| `page` | `3` | Chỉ có với PDF. |
| `section` | `Writing Task 2` | Heading nhận ra được (markdown `#`, số thứ tự, hoặc dòng ngắn VIẾT HOA). Để trống khi không chắc — thà thiếu hơn gán sai nhãn. |
| `language` | `vi` / `en` / `unknown` | Heuristic, không thêm dependency: ưu tiên dấu tiếng Việt, sau đó đếm từ chức năng. |
| `version` | `20261026-034046` | Version index chứa chunk này. |
| `metadata_schema` | `1` | Tăng khi đổi *cách* sinh ID theo kiểu không tương thích ngược. |

`chunk_id` được bảo đảm duy nhất: va chạm (cùng doc, page, ordinal) được thêm
hậu tố `-2`, `-3`… Chroma từ chối ID trùng, nên phải xử lý trước khi build.

### Chọn schema `chunk_id` thế nào

- **Theo vị trí** (`#page:ordinal`) ổn định khi nội dung chunk đó đổi nhẹ, nhưng
  dịch chuyển nếu nội dung *phía trước* trong cùng trang đổi.
- **Theo nội dung** (hash) ổn định khi sắp xếp lại, nhưng đổi ngay khi sửa chữ.

Chọn vị trí cho `chunk_id` và ghi thêm `content_hash` riêng, nên có cả hai tín
hiệu. Khi gán nhãn eval, `doc_id` là nhãn chính (bền nhất), `chunk_id` là nhãn
chi tiết.

## `index_meta.json`

Mỗi version index có một file `index_meta.json` bên trong thư mục version, ghi
**sau khi verify, trước khi activate**:

```json
{
  "schema": 1,
  "metadata_schema": 1,
  "version": "20261026-034046",
  "created_at": "2026-10-26T03:40:46Z",
  "embedding_model": "BAAI/bge-m3",
  "embedding_dim": 1024,
  "distance_metric": "",
  "num_chunks": 3,
  "num_documents": 3,
  "num_files": 3,
  "docs_dir": "data/knowledge_base",
  "chunk_size": 500,
  "chunk_overlap": 50,
  "corpus_fingerprint": "0bf31fcc909da264"
}
```

`corpus_fingerprint` là hash của toàn bộ `(doc_id, chunk_id, content_hash)` đã
sort — bất biến với thứ tự chunk, đổi ngay khi nội dung hoặc tập tài liệu đổi.
Đây là "phiên bản dữ liệu" để báo cáo eval: **hai phép đo chỉ so sánh được với
nhau khi fingerprint giống nhau**.

Thứ tự ghi có chủ đích: một version đã activate mà thiếu metadata sẽ bị coi là
"index cũ không rõ model" và lọt qua kiểm tra tương thích.

## Kiểm tra tương thích index

Bug âm thầm được chặn: **đổi `EMBEDDING_MODEL` mà không reindex**. Vector trong
index thuộc không gian của model cũ, nên truy vấn vẫn "thành công" và trả kết quả
vô nghĩa — hoặc Chroma báo một lỗi `dimension` rất khó hiểu.

Khi mở index, `index_compatibility_problem()` so metadata với cấu hình hiện tại
và từ chối nếu lệch `embedding_model`, `distance_metric`, hoặc `metadata_schema`
mới hơn code. Kiểm tra chạy **trước khi load embedder** để không mất công tải cả
model rồi mới phát hiện index không dùng được.

Kết quả:

- `RagStatus.INDEX_INCOMPATIBLE` (nằm trong `DEGRADED_STATUSES`) — tách riêng
  khỏi `RETRIEVAL_ERROR` vì việc cần làm khác nhau: đây là "phải reindex", không
  phải "thử lại sau".
- `GET /api/v1/health/ready` → **503**, kèm `index_compatible: false` và lý do.
- `POST /api/v1/rag/search` → **503**, message chỉ rõ phải chạy `POST /rag/index`.
- Lỗi `dimension mismatch` từ Chroma lúc truy xuất cũng được quy về trạng thái
  này thay vì lỗi truy xuất chung.

**Index của bản cũ không có `index_meta.json` thì KHÔNG bị chặn** — không biết nó
build bằng model gì thì không kết luận; nó sẽ chuyển sang layout có metadata ở
lần reindex tới.

### Đổi distance metric

`RAG_DISTANCE_METRIC` (trống = mặc định Chroma, tức `l2`) được ghi vào metadata.
Để trống thì không ghi `hnsw:space` vào collection, giữ nguyên hành vi cũ —
`RAGService.SCORE_THRESHOLD` đang được chuẩn theo `l2`, nên **đổi metric mà không
đổi ngưỡng sẽ làm bộ lọc `NO_EVIDENCE` sai hoàn toàn**. Đổi giá trị này thì phải
reindex; index cũ sẽ bị từ chối kèm lý do.

## Nguồn có cấu trúc ở API

`POST /api/v1/rag/search` trả `sources` gồm `doc_id`, `chunk_id`, `page`,
`section`, `language`, `content_hash`, `score` và `evidence` — đoạn ngắn quanh từ
khoá truy vấn, để người đọc thấy *vì sao* chunk này được coi là nguồn. Chunk của
index cũ (không có metadata) vẫn trả về được, các field mới là `null`.

`GET /api/v1/rag/list` cũng trả `doc_id`/`chunk_id` để soi kho tài liệu bằng ID
ổn định.
