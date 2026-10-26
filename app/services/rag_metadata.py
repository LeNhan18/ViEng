"""Metadata và ID ổn định cho chunk trong vectorstore.

Trước đây một chunk chỉ mang ``source`` (đường dẫn tuyệt đối của file trên máy
build) và ``page`` nếu là PDF. Hai hệ quả:

1. **Không gán nhãn được để đánh giá.** Một bộ eval retrieval cần nhãn kiểu
   "truy vấn Q phải lấy được tài liệu D (chunk C)". Đường dẫn tuyệt đối thay đổi
   theo máy (``E:\\...`` vs ``/app/data/...``) nên không dùng làm nhãn được, và
   chunk thì không có ID nào cả.
2. **Reindex sinh ID mới hoàn toàn.** Chroma tự cấp UUID cho mỗi chunk, nên hai
   lần index cùng một corpus cho ra hai tập ID khác nhau — không so sánh được
   giữa các version index, và không phát hiện được chunk trùng nội dung.

Module này sinh metadata ổn định, xác định (deterministic) và **không phụ thuộc
langchain** để chế độ lite cũng import được:

- ``doc_id``       đường dẫn POSIX *tương đối* so với gốc corpus → giống nhau
                   trên Windows, Ubuntu và Docker.
- ``chunk_id``     ``<doc_id>#<page>:<ordinal>`` — ổn định giữa các lần index
                   cùng một nội dung, và là duy nhất trong một index.
- ``content_hash`` sha256 (16 hex đầu) của nội dung chunk → phát hiện trùng lặp
                   và nội dung đã đổi mà không cần so cả văn bản.
- ``section``      heading gần nhất phía trên chunk (nếu nhận ra được).
- ``language``     ``vi`` / ``en`` / ``unknown`` đoán bằng heuristic, không thêm
                   dependency.
- ``version``      version index chứa chunk này.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path, PurePosixPath

#: Tăng khi thay đổi *cách* sinh metadata/ID theo kiểu không tương thích ngược.
#: Index có schema cũ hơn vẫn đọc được nhưng nhãn eval không so sánh được.
METADATA_SCHEMA_VERSION = 1

_HASH_LEN = 16

#: Tên file metadata nằm trong mỗi thư mục version index.
INDEX_META_FILE = "index_meta.json"

# Dấu thanh/nguyên âm chỉ có trong tiếng Việt (không có trong tiếng Anh).
_VI_CHARS = set("ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩị"
                "òóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ")
_VI_WORDS = re.compile(
    r"\b(của|những|được|không|người|trong|này|là|và|cho|với|các|một|khi|thì)\b"
)
_EN_WORDS = re.compile(
    r"\b(the|and|of|to|in|is|that|for|you|with|this|are|was|as|it)\b"
)

# Heading: markdown (#), số thứ tự (1. / 2.3), hoặc một dòng ngắn VIẾT HOA.
_MD_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*\S)\s*$")
_NUM_HEADING = re.compile(r"^\s{0,3}((?:\d+\.){1,3}\d*)\s+(\S.*)$")
_MAX_HEADING_LEN = 120


def content_hash(text: str) -> str:
    """Hash ổn định của nội dung chunk (16 hex đầu của sha256).

    Chuẩn hoá khoảng trắng trước khi hash để một thay đổi format vô nghĩa
    (xuống dòng khác đi) không làm đổi hash.
    """
    normalized = " ".join((text or "").split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:_HASH_LEN]


def doc_id_for(source: str, docs_root: str | Path = "") -> str:
    """ID tài liệu ổn định: đường dẫn POSIX tương đối so với gốc corpus.

    ``/app/data/knowledge_base/ielts/band.txt`` với gốc
    ``/app/data/knowledge_base`` → ``ielts/band.txt``. Trên Windows, dấu ``\\``
    được chuyển thành ``/`` nên nhãn eval dùng được trên cả hai hệ điều hành.

    Khi không suy ra được đường dẫn tương đối (source nằm ngoài gốc corpus) thì
    dùng tên file; nếu cả tên file cũng không có thì trả ``unknown``.
    """
    raw = (source or "").strip()
    if not raw:
        return "unknown"

    # Chuẩn hoá separator trước, vì PurePath của Linux không hiểu "\" của Windows.
    normalized = raw.replace("\\", "/")
    candidate = PurePosixPath(normalized)

    root = str(docs_root or "").strip().replace("\\", "/")
    if root:
        root_path = PurePosixPath(root)
        try:
            return str(candidate.relative_to(root_path))
        except ValueError:
            # Thử so khớp theo hậu tố: source có thể là đường dẫn tuyệt đối còn
            # docs_root là tương đối (hoặc ngược lại).
            parts = candidate.parts
            root_parts = root_path.parts
            for i in range(len(parts)):
                if parts[i : i + len(root_parts)] == root_parts:
                    tail = parts[i + len(root_parts) :]
                    if tail:
                        return str(PurePosixPath(*tail))
                    break

    name = candidate.name
    return name or "unknown"


def detect_language(text: str) -> str:
    """Đoán ngôn ngữ chunk: ``vi``, ``en`` hoặc ``unknown``.

    Heuristic có chủ đích (không thêm dependency): ưu tiên dấu tiếng Việt vì đó
    là tín hiệu không thể xuất hiện trong tiếng Anh; nếu không có dấu thì so số
    lượng từ chức năng của hai ngôn ngữ.
    """
    if not text or not text.strip():
        return "unknown"
    lowered = unicodedata.normalize("NFC", text.lower())

    if any(ch in _VI_CHARS for ch in lowered):
        return "vi"

    vi_hits = len(_VI_WORDS.findall(lowered))
    en_hits = len(_EN_WORDS.findall(lowered))
    if vi_hits > en_hits:
        return "vi"
    if en_hits > vi_hits:
        return "en"
    return "unknown"


def detect_section(text: str) -> str:
    """Heading mô tả chunk, lấy từ *những dòng đầu* của chunk.

    Chỉ nhận heading thật sự rõ ràng (markdown ``#``, số thứ tự, hoặc dòng ngắn
    viết hoa toàn bộ). Không đoán bừa: thà trả ``""`` còn hơn gán sai nhãn
    section cho eval.
    """
    if not text:
        return ""
    for line in text.splitlines()[:5]:
        stripped = line.strip()
        if not stripped or len(stripped) > _MAX_HEADING_LEN:
            continue

        m = _MD_HEADING.match(line)
        if m:
            return m.group(2).strip()

        m = _NUM_HEADING.match(line)
        if m:
            return f"{m.group(1)} {m.group(2)}".strip()

        letters = [c for c in stripped if c.isalpha()]
        if letters and all(c.isupper() for c in letters) and len(letters) >= 3:
            return stripped
    return ""


def _page_key(meta: dict) -> str:
    page = meta.get("page")
    if page is None or page == "":
        return "0"
    return str(page)


def enrich_chunks(
    chunks,
    docs_root: str | Path = "",
    version: str = "",
) -> list[str]:
    """Gắn metadata ổn định vào từng chunk **tại chỗ** và trả về list ``chunk_id``.

    Thứ tự ``chunk_id`` trùng thứ tự ``chunks`` để truyền thẳng vào
    ``Chroma.from_documents(ids=...)``.

    ``chunk_id`` được bảo đảm **duy nhất** trong một lần gọi: hai chunk cùng
    (doc_id, page, ordinal) — chỉ xảy ra khi upstream sinh dữ liệu lạ — sẽ được
    thêm hậu tố ``-2``, ``-3``… Chroma từ chối ID trùng, nên kiểm tra ở đây thay
    vì để lỗi xuất hiện lúc build index.
    """
    ids: list[str] = []
    seen: dict[str, int] = {}
    ordinals: dict[tuple[str, str], int] = {}

    for chunk in chunks:
        meta = chunk.metadata if isinstance(chunk.metadata, dict) else {}
        text = chunk.page_content or ""

        doc_id = doc_id_for(meta.get("source", ""), docs_root)
        page_key = _page_key(meta)
        ordinal = ordinals.get((doc_id, page_key), 0)
        ordinals[(doc_id, page_key)] = ordinal + 1

        base_id = f"{doc_id}#{page_key}:{ordinal}"
        count = seen.get(base_id, 0)
        seen[base_id] = count + 1
        chunk_id = base_id if count == 0 else f"{base_id}-{count + 1}"

        meta["doc_id"] = doc_id
        meta["chunk_id"] = chunk_id
        meta["chunk_ordinal"] = ordinal
        meta["content_hash"] = content_hash(text)
        meta["language"] = detect_language(text)
        meta["section"] = detect_section(text)
        meta["metadata_schema"] = METADATA_SCHEMA_VERSION
        if version:
            meta["version"] = version
        # Chroma chỉ nhận metadata vô hướng; `page` của PDF loader là int, giữ
        # nguyên. `source` giữ nguyên để không phá _format_context và caller cũ.
        if "page" not in meta and page_key != "0":
            meta["page"] = int(page_key) if page_key.isdigit() else page_key

        chunk.metadata = {k: v for k, v in meta.items() if v is not None}
        ids.append(chunk_id)

    return ids


def corpus_fingerprint(chunks) -> str:
    """Hash của cả corpus đã chunk — "phiên bản dữ liệu" tái lập được.

    Dùng để ghi vào metadata của index và vào báo cáo eval: hai lần đo chỉ so
    sánh được với nhau khi fingerprint giống nhau.

    Bất biến với thứ tự chunk (sort trước khi hash) nhưng đổi ngay khi nội dung
    hoặc tập tài liệu đổi.
    """
    h = hashlib.sha256()
    entries = []
    for chunk in chunks:
        meta = chunk.metadata if isinstance(chunk.metadata, dict) else {}
        entries.append(
            f"{meta.get('doc_id', '')}|{meta.get('chunk_id', '')}|"
            f"{meta.get('content_hash') or content_hash(chunk.page_content or '')}"
        )
    for entry in sorted(entries):
        h.update(entry.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()[:_HASH_LEN]


def evidence_snippet(text: str, query: str = "", max_len: int = 240) -> str:
    """Đoạn ngắn trong chunk để trả về làm bằng chứng.

    Ưu tiên cửa sổ quanh từ khoá đầu tiên của truy vấn xuất hiện trong chunk;
    nếu không khớp từ nào thì lấy phần đầu. Mục đích là người đọc thấy *vì sao*
    chunk này được coi là nguồn, chứ không phải đọc lại cả chunk.
    """
    body = " ".join((text or "").split())
    if not body:
        return ""
    if len(body) <= max_len:
        return body

    start = 0
    terms = [t for t in re.findall(r"\w+", (query or "").lower()) if len(t) > 3]
    lowered = body.lower()
    for term in terms:
        pos = lowered.find(term)
        if pos != -1:
            start = max(0, pos - max_len // 3)
            break

    end = start + max_len
    snippet = body[start:end]
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(body) else ""
    return f"{prefix}{snippet.strip()}{suffix}"


def read_index_meta(version_dir: Path | str) -> dict:
    """Đọc ``index_meta.json`` của một version index; trả ``{}`` nếu không có.

    Index tạo bởi bản cũ (chưa có file này) là hợp lệ — chỉ là "không biết" nó
    được build bằng model nào, nên không chặn load.
    """
    import json

    path = Path(version_dir) / INDEX_META_FILE
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_index_meta(version_dir: Path | str, meta: dict) -> Path:
    """Ghi ``index_meta.json`` cho một version index (ghi tạm rồi replace)."""
    import json
    import os

    target = Path(version_dir) / INDEX_META_FILE
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(tmp, target)
    return target



def compatibility_problem(meta: dict, embedding_model: str, distance_metric: str) -> str:
    """Lý do index không dùng được với cấu hình hiện tại; ``""`` nếu dùng được.

    Trường hợp thật đang bị bỏ lọt: đổi ``EMBEDDING_MODEL`` mà không reindex.
    Vector trong index thuộc không gian của model cũ, nên truy vấn vẫn "thành
    công" nhưng kết quả là rác (hoặc Chroma báo lỗi dimension khó hiểu). Phát
    hiện ngay lúc mở index thì thông báo được rõ ràng là phải reindex.

    Index không có metadata (bản cũ) → không kết luận, trả ``""``.
    """
    if not meta:
        return ""

    indexed_model = str(meta.get("embedding_model") or "").strip()
    if indexed_model and embedding_model and indexed_model != embedding_model:
        return (
            f"Index được build bằng embedding model '{indexed_model}' nhưng cấu "
            f"hình hiện tại là '{embedding_model}'. Vector không cùng không gian "
            f"— hãy chạy lại POST /rag/index (hoặc đặt EMBEDDING_MODEL về "
            f"'{indexed_model}')."
        )

    indexed_metric = str(meta.get("distance_metric") or "").strip()
    if indexed_metric and distance_metric and indexed_metric != distance_metric:
        return (
            f"Index dùng distance metric '{indexed_metric}' nhưng cấu hình hiện "
            f"tại là '{distance_metric}'. Ngưỡng điểm không còn đúng — hãy reindex."
        )

    schema = meta.get("metadata_schema")
    if isinstance(schema, int) and schema > METADATA_SCHEMA_VERSION:
        return (
            f"Index dùng metadata schema v{schema}, code này chỉ hiểu tới "
            f"v{METADATA_SCHEMA_VERSION}. Hãy cập nhật code hoặc reindex."
        )
    return ""


def looks_like_dimension_mismatch(error: BaseException) -> bool:
    """Lỗi từ Chroma có phải do số chiều vector không khớp?

    Dùng để quy một lỗi truy xuất mơ hồ về đúng nguyên nhân (index build bằng
    model khác) thay vì báo chung chung "lỗi truy xuất".
    """
    text = f"{type(error).__name__}: {error}".lower()
    return "dimension" in text and (
        "match" in text or "expecting" in text or "mismatch" in text or "!=" in text
    )
