"""RAG pipeline: indexing knowledge base và truy xuất context.

Hai thay đổi nền tảng so với bản đầu:

1. **Trạng thái tường minh.** Trước đây mọi tình huống — RAG bị tắt, index chưa
   tạo, embedder lỗi, truy xuất lỗi, không tìm được bằng chứng — đều trả về ``""``
   nên caller không thể phân biệt "không có tài liệu nào khớp" với "hệ thống đang
   hỏng". Giờ ``retrieve_detailed()`` trả về :class:`RetrievalResult` có
   :class:`RagStatus`; các hàm trả string cũ được giữ nguyên chữ ký để không phá
   caller hiện tại.

2. **Reindex an toàn.** Trước đây ``index_knowledge_base`` xoá vectorstore cũ
   (``shutil.rmtree``) *trước khi* build cái mới, nên build lỗi là mất luôn index
   đang chạy. Giờ build vào thư mục staging riêng, verify bằng một truy vấn thật,
   rồi mới swap; index cũ được giữ lại để rollback.
"""

from __future__ import annotations

import shutil
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from loguru import logger

from app.core.config import get_settings


class RagStatus(str, Enum):
    """Vì sao một lần truy xuất không trả được bằng chứng (hoặc là trả được)."""

    OK = "ok"
    DISABLED = "disabled"
    EMBEDDER_UNAVAILABLE = "embedder_unavailable"
    INDEX_NOT_READY = "index_not_ready"
    RETRIEVAL_ERROR = "retrieval_error"
    NO_EVIDENCE = "no_evidence"


#: Những trạng thái nghĩa là "hệ thống có vấn đề", khác với NO_EVIDENCE
#: (hệ thống chạy đúng nhưng kho tài liệu không có gì khớp).
DEGRADED_STATUSES = frozenset({
    RagStatus.EMBEDDER_UNAVAILABLE,
    RagStatus.INDEX_NOT_READY,
    RagStatus.RETRIEVAL_ERROR,
})


@dataclass
class RetrievalResult:
    """Kết quả một lần truy xuất, kèm lý do khi rỗng."""

    status: RagStatus
    documents: list = field(default_factory=list)   # list[(Document, score|None)]
    context: str = ""
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status is RagStatus.OK

    @property
    def degraded(self) -> bool:
        return self.status in DEGRADED_STATUSES

    def as_dict(self) -> dict:
        return {
            "status": self.status.value,
            "detail": self.detail,
            "num_documents": len(self.documents),
            "context": self.context,
        }


def _format_context(docs) -> str:
    """Ghép các doc thành context cho prompt (giữ đúng format cũ)."""
    return "\n\n---\n\n".join(
        f"[Nguồn: {doc.metadata.get('source', 'N/A')}]\n{doc.page_content}"
        for doc in docs
    )


_PROBE_QUERY = "English grammar"

# Layout trên đĩa của vectorstore:
#   <root>/CURRENT            -> text file chứa tên version đang dùng
#   <root>/versions/<ver>/    -> dữ liệu Chroma của từng version
# Reindex build vào version MỚI rồi chỉ đổi con trỏ CURRENT, KHÔNG rename thư mục
# đang được dùng. Lý do: ChromaDB cache client theo *đường dẫn*, nên nếu đổi tên
# thư mục bên dưới nó, handle cũ vẫn trỏ vào inode cũ và truy vấn trả dữ liệu cũ
# (bug này bị bắt bởi test e2e, unit test dùng fake store không thấy được).
_CURRENT_FILE = "CURRENT"
_VERSIONS_DIR = "versions"
_LEGACY_MARKER = "chroma.sqlite3"
# Đánh dấu một version đang build. Xoá marker = version đã verify xong.
# Cần marker vì KHÔNG được rmtree thư mục của một client Chroma còn sống: làm vậy
# phá trạng thái sqlite của cả tiến trình và mọi lần reindex sau đều fail
# "attempt to write a readonly database". Khi build lỗi ta để lại thư mục (có
# marker) và dọn ở đầu lần reindex kế tiếp, lúc không còn client nào mở.
_INCOMPLETE_MARKER = ".incomplete"
# Thời điểm tiến trình này bắt đầu. Chỉ dọn version lỗi CŨ HƠN mốc này: version
# lỗi do chính tiến trình này tạo ra có thể vẫn còn client Chroma sống (traceback
# của exception giữ frame), và rmtree lúc đó phá trạng thái sqlite toàn tiến trình.
_PROCESS_START = time.time()


class RAGService:
    """Quản lý RAG pipeline: indexing knowledge base và truy xuất context."""

    SCORE_THRESHOLD = 1.2

    def __init__(self):
        settings = get_settings()
        self._embeddings = None
        self._vectorstore = None
        self._root = Path(settings.chroma_persist_dir)
        self._persist_dir = settings.chroma_persist_dir
        self._embedding_model = settings.embedding_model
        self._enabled = bool(settings.rag_enabled)
        self._keep_old = max(0, int(settings.rag_keep_old_indexes))
        # Cờ ghi nhớ load embedder/vectorstore thất bại để khỏi thử lại liên tục
        # và đỡ spam log. reset() xoá cờ sau khi reindex thành công.
        self._embedder_broken = False
        self._vectorstore_broken = False
        self._last_error = ""
        # Chỉ cho một lần reindex chạy tại một thời điểm.
        self._index_lock = threading.Lock()

    # ------------------------------------------------------------------ state

    def reset(self) -> None:
        """Bỏ cache embedder/vectorstore và các cờ lỗi (dùng sau reindex)."""
        self._vectorstore = None
        self._vectorstore_broken = False
        self._embedder_broken = False
        self._last_error = ""

    def _release_vectorstore(self) -> None:
        """Thả handle Chroma trước khi rename thư mục (bắt buộc trên Windows).

        CHÚ Ý: không gọi ``client.reset()`` — trong ChromaDB đó là lệnh **xoá sạch
        dữ liệu**, không phải "đóng kết nối". Gọi nó ở đây sẽ xoá rỗng index đang
        chạy ngay trước khi rename, nên bản .old-* giữ lại thành vô dụng.
        Cách đúng là bỏ hết reference rồi để GC đóng handle.
        """
        self._vectorstore = self._close_store(self._vectorstore)

    @staticmethod
    def _close_store(store):
        """Bỏ reference tới một vectorstore rồi gc, trả về None.

        Dùng trước khi xoá/đổi thư mục của nó. Xem chú thích ở _release_vectorstore
        về việc KHÔNG dùng client.reset().
        """
        import gc

        if store is None:
            return None
        del store
        gc.collect()
        return None

    def _ensure_enabled(self) -> bool:
        return bool(self._enabled)

    # --- layout version hoá -------------------------------------------------

    @property
    def _versions_root(self) -> Path:
        return self._root / _VERSIONS_DIR

    @property
    def _current_file(self) -> Path:
        return self._root / _CURRENT_FILE

    def _read_current(self) -> str:
        try:
            return self._current_file.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def _write_current(self, version: str) -> None:
        """Đổi con trỏ CURRENT bằng os.replace (atomic trên cùng filesystem)."""
        import os

        self._root.mkdir(parents=True, exist_ok=True)
        tmp = self._current_file.with_name(_CURRENT_FILE + ".tmp")
        tmp.write_text(version, encoding="utf-8")
        os.replace(tmp, self._current_file)

    def _is_legacy_layout(self) -> bool:
        """Index cũ ghi thẳng vào <root> (trước khi có version hoá)."""
        return (self._root / _LEGACY_MARKER).exists()

    def active_index_path(self) -> Path | None:
        """Thư mục Chroma đang dùng, hoặc None nếu chưa có index nào."""
        version = self._read_current()
        if version:
            candidate = self._versions_root / version
            # Marker .incomplete là thứ quyết định version đã dùng được hay chưa;
            # không cần kiểm tra "thư mục không rỗng" nữa.
            if candidate.is_dir() and not (candidate / _INCOMPLETE_MARKER).exists():
                return candidate
        if self._is_legacy_layout():
            # Tương thích ngược: dùng tiếp index cũ cho tới lần reindex tới.
            return self._root
        return None

    def active_version(self) -> str:
        path = self.active_index_path()
        if path is None:
            return ""
        return "legacy" if path == self._root else path.name

    def _index_exists(self) -> bool:
        try:
            return self.active_index_path() is not None
        except OSError:
            return False

    def status(self) -> dict:
        """Ảnh chụp trạng thái RAG cho health/readiness và debug."""
        index_present = self._index_exists()
        if not self._enabled:
            overall = RagStatus.DISABLED
        elif self._embedder_broken:
            overall = RagStatus.EMBEDDER_UNAVAILABLE
        elif self._vectorstore_broken:
            overall = RagStatus.RETRIEVAL_ERROR
        elif not index_present:
            overall = RagStatus.INDEX_NOT_READY
        else:
            overall = RagStatus.OK

        return {
            "status": overall.value,
            "enabled": self._enabled,
            "ready": overall is RagStatus.OK,
            "embedding_model": self._embedding_model,
            "embedder": (
                "broken" if self._embedder_broken
                else ("loaded" if self._embeddings is not None else "not_loaded")
            ),
            "index": {
                "present": index_present,
                "persist_dir": self._persist_dir,
                "version": self.active_version(),
                "active_path": str(self.active_index_path() or ""),
                "available_versions": self.list_versions(),
                "loaded": self._vectorstore is not None,
                "broken": self._vectorstore_broken,
                "num_chunks": self._count_chunks(),
            },
            "last_error": self._last_error,
        }

    def _count_chunks(self) -> int | None:
        """Số chunk trong index nếu đọc được rẻ; None nếu chưa load/không đọc được."""
        vs = self._vectorstore
        if vs is None:
            return None
        try:
            return int(vs._collection.count())
        except Exception:  # noqa: BLE001 - phiên bản Chroma khác nhau
            return None

    def is_ready(self) -> bool:
        """RAG bật, embedder ổn và index có mặt."""
        return bool(
            self._enabled
            and not self._embedder_broken
            and not self._vectorstore_broken
            and self._index_exists()
        )

    # ------------------------------------------------------------- components

    def _get_embeddings(self):
        if not self._ensure_enabled() or self._embedder_broken:
            return None
        if self._embeddings is None:
            try:
                # Lazy import để chế độ "lite" không cần cài langchain/sentence-transformers.
                from langchain_community.embeddings import HuggingFaceEmbeddings

                from app.core.paths import configure_hf_env, hf_cache_dir

                settings = get_settings()
                configure_hf_env(hf_cache_dir(settings.hf_cache_dir, settings.cache_dir))

                self._embeddings = HuggingFaceEmbeddings(
                    model_name=self._embedding_model,
                    model_kwargs={"device": "cpu"},
                )
            except Exception as e:
                self._embedder_broken = True
                self._last_error = f"embedder: {type(e).__name__}: {e}"
                logger.warning(
                    "Không khởi tạo được embedder ({}). RAG sẽ tạm thời không hoạt động "
                    "— pipeline chat vẫn chạy bình thường.",
                    e,
                )
                return None
        return self._embeddings

    def _get_vectorstore(self):
        if not self._ensure_enabled() or self._vectorstore_broken:
            return None
        if self._vectorstore is None:
            try:
                from langchain_community.vectorstores import Chroma

                active = self.active_index_path()
                if active is None:
                    logger.warning(
                        "Vectorstore chưa được tạo. Hãy chạy index_knowledge_base() trước."
                    )
                    return None
                embeddings = self._get_embeddings()
                if embeddings is None:
                    # Embedder broken -> không thể truy vấn vectorstore.
                    self._vectorstore_broken = True
                    return None
                self._vectorstore = Chroma(
                    persist_directory=str(active),
                    embedding_function=embeddings,
                )
                logger.info(f"Loaded vectorstore from {active}")
            except Exception as e:
                self._vectorstore_broken = True
                self._last_error = f"vectorstore: {type(e).__name__}: {e}"
                logger.warning(
                    "Không load được vectorstore ({}). RAG tắt cho phiên này.", e
                )
                return None
        return self._vectorstore

    def _resolve_store(self) -> tuple[object | None, RetrievalResult | None]:
        """-> (vectorstore, None) khi dùng được; (None, RetrievalResult lỗi) khi không."""
        if not self._ensure_enabled():
            return None, RetrievalResult(
                RagStatus.DISABLED, detail="RAG_ENABLED=false"
            )
        if self._embedder_broken:
            return None, RetrievalResult(
                RagStatus.EMBEDDER_UNAVAILABLE, detail=self._last_error
            )
        if not self._index_exists():
            return None, RetrievalResult(
                RagStatus.INDEX_NOT_READY,
                detail=f"Chưa có index tại {self._root}",
            )
        vs = self._get_vectorstore()
        if vs is None:
            status = (
                RagStatus.EMBEDDER_UNAVAILABLE if self._embedder_broken
                else RagStatus.RETRIEVAL_ERROR
            )
            return None, RetrievalResult(status, detail=self._last_error)
        return vs, None

    # --------------------------------------------------------------- indexing

    def _load_documents(self, docs_dir: str) -> list:
        """Đọc .txt và .pdf từ docs_dir thành list[Document]."""
        from langchain_community.document_loaders import DirectoryLoader, TextLoader
        from langchain_core.documents import Document

        docs_path = Path(docs_dir)
        documents: list = []

        has_txt = any(docs_path.glob("**/*.txt")) or any(
            docs_path.glob("**/IELTS_writting_band_decriptors")
        )
        if has_txt:
            txt_loader = DirectoryLoader(
                docs_dir,
                glob=["**/*.txt", "**/IELTS_writting_band_decriptors"],
                loader_cls=TextLoader,
                loader_kwargs={"encoding": "utf-8"},
            )
            documents.extend(txt_loader.load())

        import re

        from app.services.ocr_service import ocr_service

        for pdf_file in sorted(docs_path.glob("**/*.pdf")):
            try:
                pdf_bytes = pdf_file.read_bytes()
                extracted_text = ocr_service._ocr_pdf_pages(pdf_bytes, max_pages=9999)

                docs = []
                # Tách văn bản theo từng trang dựa trên marker [Trang X]
                parts = re.split(r"\[Trang (\d+)\]\n", extracted_text)
                if len(parts) > 1:
                    for idx in range(1, len(parts), 2):
                        page_num = int(parts[idx])
                        page_content = parts[idx + 1].strip()
                        if page_content:
                            docs.append(Document(
                                page_content=page_content,
                                metadata={"source": str(pdf_file), "page": page_num},
                            ))
                else:
                    content = extracted_text.strip()
                    if content:
                        docs.append(Document(
                            page_content=content,
                            metadata={"source": str(pdf_file)},
                        ))

                documents.extend(docs)
                logger.info(
                    f"Đã load PDF bằng PP-StructureV3: {pdf_file.name} ({len(docs)} trang)"
                )
            except Exception as e:
                logger.warning(f"Không load được PDF {pdf_file.name}: {e}")

        return documents

    def _cleanup_incomplete(self) -> None:
        """Dọn các version build lỗi còn sót từ lần trước.

        Chạy ở ĐẦU mỗi lần reindex, khi chắc chắn không có client Chroma nào mở
        trên chúng — xem chú thích ở _INCOMPLETE_MARKER.
        """
        root = self._versions_root
        if not root.exists():
            return
        try:
            candidates = [p for p in root.iterdir() if p.is_dir()]
        except OSError:
            return
        for d in candidates:
            marker = d / _INCOMPLETE_MARKER
            if not marker.exists():
                continue
            try:
                if marker.stat().st_mtime >= _PROCESS_START:
                    # Do chính tiến trình này tạo -> để lần chạy sau dọn.
                    logger.info(
                        "Bỏ qua version lỗi {} (tạo trong tiến trình này); sẽ dọn "
                        "sau khi restart.", d.name,
                    )
                    continue
                shutil.rmtree(d)
                logger.info("Đã dọn version build lỗi còn sót: {}", d.name)
            except OSError as e:
                logger.warning("Không dọn được version {}: {}", d.name, e)

    def _new_version(self) -> str:
        """Tên version mới, đảm bảo không đụng version đã có trong cùng giây."""
        base = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
        version = base
        suffix = 1
        while (self._versions_root / version).exists():
            version = f"{base}-{suffix}"
            suffix += 1
        return version

    def list_versions(self) -> list[str]:
        """Các version index có trên đĩa, mới nhất trước."""
        root = self._versions_root
        if not root.exists():
            return []
        try:
            return sorted(
                (
                    p.name for p in root.iterdir()
                    if p.is_dir() and not (p / _INCOMPLETE_MARKER).exists()
                ),
                reverse=True,
            )
        except OSError:
            return []

    def _activate_version(self, version: str) -> None:
        """Trỏ CURRENT sang `version` rồi dọn các version cũ quá hạn giữ."""
        self._release_vectorstore()
        self._write_current(version)
        logger.info("Đã kích hoạt index version {}", version)
        self._prune_old_versions(keep_current=version)

    def _prune_old_versions(self, keep_current: str) -> None:
        """Giữ version đang dùng + `rag_keep_old_indexes` bản gần nhất."""
        others = [v for v in self.list_versions() if v != keep_current]
        for stale in others[self._keep_old:]:
            try:
                shutil.rmtree(self._versions_root / stale)
                logger.info("Đã xoá index version cũ {}", stale)
            except OSError as e:
                logger.warning("Không xoá được index version {}: {}", stale, e)

    def rollback(self, version: str = "") -> str:
        """Quay về một version index cũ (mặc định: bản gần nhất trước bản đang dùng).

        Trả về version được kích hoạt. Raise nếu không có bản nào để quay về.
        """
        current = self.active_version()
        available = self.list_versions()
        if version:
            if version not in available:
                raise RuntimeError(f"Không có index version {version}.")
            target = version
        else:
            candidates = [v for v in available if v != current]
            if not candidates:
                raise RuntimeError("Không có version cũ nào để rollback.")
            target = candidates[0]
        self._activate_version(target)
        self.reset()
        return target

    def index_knowledge_base(self, docs_dir: str = "data/knowledge_base") -> int:
        """Build index mới vào staging, verify, rồi swap. Trả về số chunks.

        Index đang chạy chỉ bị thay khi bản mới build *và* verify xong, nên build
        lỗi không làm mất index cũ.
        """
        if not self._ensure_enabled():
            logger.info("RAG disabled (RAG_ENABLED=false) — skip indexing knowledge base.")
            return 0

        if not self._index_lock.acquire(blocking=False):
            logger.warning("Một tiến trình reindex khác đang chạy — bỏ qua lần này.")
            raise RuntimeError("Đang có một tiến trình reindex khác chạy.")

        staging: Path | None = None
        staged_store = None
        try:
            self._cleanup_incomplete()
            # Kiểm tra dữ liệu trước khi import stack nặng: thư mục rỗng là tình
            # huống bình thường, không nên biến thành ModuleNotFoundError ở lite mode.
            docs_path = Path(docs_dir)
            has_txt = any(docs_path.glob("**/*.txt")) or any(
                docs_path.glob("**/IELTS_writting_band_decriptors")
            )
            has_pdf = any(docs_path.glob("**/*.pdf"))
            if not docs_path.exists() or (not has_txt and not has_pdf):
                logger.warning(f"Không tìm thấy tài liệu .txt hoặc .pdf trong {docs_dir}")
                return 0

            try:
                from langchain_community.vectorstores import Chroma
                from langchain_text_splitters import RecursiveCharacterTextSplitter
            except ImportError as e:
                # Chế độ lite: requirements.lite.txt không có langchain. Nói rõ ra
                # chứ không để traceback ModuleNotFoundError lọt lên API.
                self._last_error = f"rag stack missing: {e}"
                raise RuntimeError(
                    "Stack RAG chưa được cài (cần langchain + sentence-transformers). "
                    "Dùng requirements.txt thay vì requirements.lite.txt."
                ) from e

            documents = self._load_documents(docs_dir)
            if not documents:
                logger.warning("Không load được tài liệu nào")
                return 0

            loaded_names = sorted({
                Path(d.metadata.get("source", "")).name
                for d in documents if d.metadata.get("source")
            })
            logger.info(
                f"Đã load {len(documents)} doc từ {len(loaded_names)} file: "
                f"{', '.join(loaded_names[:10])}{'...' if len(loaded_names) > 10 else ''}"
            )

            splitter = RecursiveCharacterTextSplitter(
                chunk_size=500,
                chunk_overlap=50,
                separators=["\n\n", "\n", ". ", " ", ""],
            )
            chunks = splitter.split_documents(documents)
            if not chunks:
                logger.warning("Chia chunks xong không còn nội dung nào — giữ index cũ.")
                return 0

            embeddings = self._get_embeddings()
            if embeddings is None:
                raise RuntimeError(
                    "Embedder không khả dụng, không thể build index: " + self._last_error
                )

            version = self._new_version()
            staging = self._versions_root / version
            if staging.exists():
                shutil.rmtree(staging)
            staging.mkdir(parents=True)
            (staging / _INCOMPLETE_MARKER).write_text("building", encoding="utf-8")

            staged_store = Chroma.from_documents(
                documents=chunks,
                embedding=embeddings,
                persist_directory=str(staging),
            )

            # Verify: index phải có đúng số chunk và trả lời được một truy vấn thật.
            self._verify_staged(staged_store, expected=len(chunks))
            staged_store = self._close_store(staged_store)
            (staging / _INCOMPLETE_MARKER).unlink(missing_ok=True)

            # Chỉ đổi con trỏ CURRENT khi bản mới đã verify xong. Version cũ vẫn
            # nằm nguyên trên đĩa -> rollback() quay về được.
            self._activate_version(version)
            staging = None       # đã kích hoạt, không cần cleanup
            self.reset()

            logger.info(f"Indexed {len(chunks)} chunks from {len(documents)} documents")
            return len(chunks)
        finally:
            staged_store = self._close_store(staged_store)
            if staging is not None and staging.exists():
                # Build/verify lỗi. KHÔNG xoá thư mục ở đây: client Chroma của nó
                # có thể còn sống (traceback của exception đang bay vẫn giữ frame),
                # và rmtree lúc đó phá trạng thái sqlite của cả tiến trình khiến
                # MỌI lần reindex sau đều fail. Để lại kèm marker .incomplete —
                # list_versions() bỏ qua nó và _cleanup_incomplete() dọn ở lần sau.
                logger.warning(
                    "Reindex thất bại — giữ nguyên index cũ; version lỗi {} được "
                    "đánh dấu .incomplete và sẽ dọn sau khi restart.", staging.name,
                )
            self._index_lock.release()

    def _verify_staged(self, store, expected: int) -> None:
        """Raise nếu index staging không dùng được (rỗng, thiếu, hay query lỗi).

        Bỏ reference `store` TRƯỚC khi raise: nếu không, traceback của exception
        giữ frame này sống và client Chroma không được đóng — xem _INCOMPLETE_MARKER.
        """
        problem = ""
        try:
            count = int(store._collection.count())
        except Exception as e:  # noqa: BLE001
            count, problem = -1, f"Không đọc được số chunk của index mới: {e}"

        if not problem:
            if count <= 0:
                problem = "Index mới rỗng sau khi build."
            elif count != expected:
                problem = f"Index mới có {count} chunk, kỳ vọng {expected}."

        if not problem:
            try:
                store.similarity_search(_PROBE_QUERY, k=1)
            except Exception as e:  # noqa: BLE001
                problem = f"Index mới không trả lời được truy vấn thử: {e}"

        store = None          # noqa: F841 - bỏ ref trước khi raise (có chủ đích)
        if problem:
            raise RuntimeError(problem)

    # -------------------------------------------------------------- retrieval

    def retrieve_detailed(self, query: str, k: int = 3) -> RetrievalResult:
        """Truy xuất kèm trạng thái tường minh (API nên dùng cho code mới)."""
        vs, failure = self._resolve_store()
        if failure is not None:
            return failure
        try:
            docs = vs.similarity_search(query, k=k)
        except Exception as e:
            self._last_error = f"similarity_search: {type(e).__name__}: {e}"
            logger.warning("RAG similarity_search lỗi, bỏ qua context: {}", e)
            return RetrievalResult(RagStatus.RETRIEVAL_ERROR, detail=self._last_error)
        if not docs:
            return RetrievalResult(
                RagStatus.NO_EVIDENCE, detail="Không có chunk nào khớp truy vấn."
            )
        return RetrievalResult(
            RagStatus.OK,
            documents=[(d, None) for d in docs],
            context=_format_context(docs),
        )

    def retrieve_mmr_detailed(
        self, query: str, k: int = 3, fetch_k: int = 10, lambda_mult: float = 0.7
    ) -> RetrievalResult:
        """MMR kèm trạng thái tường minh."""
        vs, failure = self._resolve_store()
        if failure is not None:
            return failure
        try:
            docs = vs.max_marginal_relevance_search(
                query, k=k, fetch_k=fetch_k, lambda_mult=lambda_mult,
            )
        except Exception as e:
            self._last_error = f"mmr: {type(e).__name__}: {e}"
            logger.warning("RAG MMR lỗi, bỏ qua context: {}", e)
            return RetrievalResult(RagStatus.RETRIEVAL_ERROR, detail=self._last_error)
        if not docs:
            return RetrievalResult(
                RagStatus.NO_EVIDENCE, detail="Không có chunk nào khớp truy vấn."
            )
        return RetrievalResult(
            RagStatus.OK,
            documents=[(d, None) for d in docs],
            context=_format_context(docs),
        )

    def retrieve_with_scores_detailed(self, query: str, k: int = 5) -> RetrievalResult:
        """Truy xuất kèm score, lọc theo threshold, kèm trạng thái tường minh.

        Lưu ý: hết kết quả *sau khi lọc threshold* là NO_EVIDENCE, không phải lỗi.
        """
        vs, failure = self._resolve_store()
        if failure is not None:
            return failure
        try:
            results = vs.similarity_search_with_score(query, k=k)
        except Exception as e:
            self._last_error = f"similarity_search_with_score: {type(e).__name__}: {e}"
            logger.warning("RAG similarity_search_with_score lỗi, trả về rỗng: {}", e)
            return RetrievalResult(RagStatus.RETRIEVAL_ERROR, detail=self._last_error)
        filtered = [(doc, score) for doc, score in results if score <= self.SCORE_THRESHOLD]
        if not filtered:
            return RetrievalResult(
                RagStatus.NO_EVIDENCE,
                detail=(
                    f"{len(results)} chunk được truy xuất nhưng không chunk nào "
                    f"vượt ngưỡng score <= {self.SCORE_THRESHOLD}."
                ),
            )
        return RetrievalResult(
            RagStatus.OK,
            documents=filtered,
            context=_format_context([d for d, _ in filtered]),
        )

    # --- API string cũ: giữ nguyên chữ ký để không phá caller hiện tại --------

    def retrieve(self, query: str, k: int = 3) -> str:
        """Truy xuất context liên quan từ knowledge base."""
        return self.retrieve_detailed(query, k=k).context

    def retrieve_with_scores(self, query: str, k: int = 5) -> list[tuple]:
        """Truy xuất kèm điểm similarity, lọc theo threshold."""
        return self.retrieve_with_scores_detailed(query, k=k).documents

    def retrieve_mmr(
        self, query: str, k: int = 3, fetch_k: int = 10, lambda_mult: float = 0.7
    ) -> str:
        """Truy xuất dùng MMR (Maximal Marginal Relevance) để tăng đa dạng kết quả."""
        return self.retrieve_mmr_detailed(
            query, k=k, fetch_k=fetch_k, lambda_mult=lambda_mult
        ).context

    def retrieve_for_topic(self, topic: str, k: int = 3) -> str:
        """Retrieve context phù hợp cho 1 chủ đề ngữ pháp/từ vựng cụ thể."""
        query = f"English grammar rules for {topic}, examples and tips for TOEIC"
        return self.retrieve_mmr(query, k=k)


rag_service = RAGService()


def create_standalone_retriever(
    docs_dir: str = "data/knowledge_base",
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    persist_dir: str = "./data/vectorstore",
):
    """Tạo retriever standalone (dùng trong scripts, không cần FastAPI)."""
    from langchain_community.document_loaders import DirectoryLoader, TextLoader
    from langchain_community.embeddings import HuggingFaceEmbeddings
    from langchain_community.vectorstores import Chroma
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    embeddings = HuggingFaceEmbeddings(
        model_name=embedding_model,
        model_kwargs={"device": "cpu"},
    )

    persist_path = Path(persist_dir)
    if persist_path.exists() and any(persist_path.iterdir()):
        vectorstore = Chroma(
            persist_directory=persist_dir,
            embedding_function=embeddings,
        )
    else:
        docs_path = Path(docs_dir)
        if not docs_path.exists() or not any(docs_path.glob("*.txt")):
            return None

        loader = DirectoryLoader(
            docs_dir,
            glob="**/*.txt",
            loader_cls=TextLoader,
            loader_kwargs={"encoding": "utf-8"},
        )
        documents = loader.load()

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=500, chunk_overlap=50,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        chunks = splitter.split_documents(documents)

        vectorstore = Chroma.from_documents(
            documents=chunks,
            embedding=embeddings,
            persist_directory=persist_dir,
        )

    def retrieve(query: str, k: int = 3) -> str:
        results = vectorstore.max_marginal_relevance_search(query, k=k, fetch_k=10)
        if not results:
            return ""
        return "\n\n---\n\n".join(
            f"[Nguồn: {doc.metadata.get('source', 'N/A')}]\n{doc.page_content}"
            for doc in results
        )

    return retrieve
