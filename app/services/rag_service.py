from app.core.config import get_settings
from loguru import logger
from pathlib import Path


class RAGService:
    """Quản lý RAG pipeline: indexing knowledge base và truy xuất context."""

    SCORE_THRESHOLD = 1.2

    def __init__(self):
        settings = get_settings()
        self._embeddings = None
        self._vectorstore = None
        self._persist_dir = settings.chroma_persist_dir
        self._embedding_model = settings.embedding_model
        self._enabled = bool(settings.rag_enabled)
        # Cờ ghi nhớ load embedder/vectorstore thất bại để khỏi thử lại liên tục
        # và đỡ spam log. Khi đó RAG hoạt động ở chế độ no-op (trả "" / []).
        self._embedder_broken = False
        self._vectorstore_broken = False

    def _ensure_enabled(self) -> bool:
        if not self._enabled:
            return False
        return True

    def _get_embeddings(self):
        if not self._ensure_enabled() or self._embedder_broken:
            return None
        if self._embeddings is None:
            try:
                # Lazy import để chế độ "lite" không cần cài langchain/sentence-transformers.
                from langchain_community.embeddings import HuggingFaceEmbeddings

                self._embeddings = HuggingFaceEmbeddings(
                    model_name=self._embedding_model,
                    model_kwargs={"device": "cpu"},
                )
            except Exception as e:
                self._embedder_broken = True
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

                persist_path = Path(self._persist_dir)
                if persist_path.exists() and any(persist_path.iterdir()):
                    embeddings = self._get_embeddings()
                    if embeddings is None:
                        # Embedder broken -> không thể truy vấn vectorstore.
                        self._vectorstore_broken = True
                        return None
                    self._vectorstore = Chroma(
                        persist_directory=self._persist_dir,
                        embedding_function=embeddings,
                    )
                    logger.info(f"Loaded vectorstore from {self._persist_dir}")
                else:
                    logger.warning(
                        "Vectorstore chưa được tạo. Hãy chạy index_knowledge_base() trước."
                    )
                    return None
            except Exception as e:
                self._vectorstore_broken = True
                logger.warning(
                    "Không load được vectorstore ({}). RAG tắt cho phiên này.", e
                )
                return None
        return self._vectorstore

    def index_knowledge_base(self, docs_dir: str = "data/knowledge_base") -> int:
        """Đọc tài liệu từ thư mục (.txt, .pdf), chia chunks, tạo embeddings và lưu vào ChromaDB."""
        if not self._ensure_enabled():
            logger.info("RAG disabled (RAG_ENABLED=false) — skip indexing knowledge base.")
            return 0

        from langchain_community.vectorstores import Chroma
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        from langchain_community.document_loaders import DirectoryLoader, TextLoader, PyPDFLoader

        docs_path = Path(docs_dir)
        has_txt = any(docs_path.glob("**/*.txt")) or any(docs_path.glob("**/IELTS_writting_band_decriptors"))
        has_pdf = any(docs_path.glob("**/*.pdf"))
        if not docs_path.exists() or (not has_txt and not has_pdf):
            logger.warning(f"Không tìm thấy tài liệu .txt hoặc .pdf trong {docs_dir}")
            return 0

        persist_path = Path(self._persist_dir)
        if persist_path.exists():
            import shutil
            shutil.rmtree(persist_path)
            logger.info(f"Đã xóa vectorstore cũ tại {self._persist_dir} để index lại từ đầu")
        persist_path.mkdir(parents=True, exist_ok=True)

        documents: list = []

        # Load .txt
        if has_txt:
            txt_loader = DirectoryLoader(
                docs_dir,
                glob=["**/*.txt", "**/IELTS_writting_band_decriptors"],
                loader_cls=TextLoader,
                loader_kwargs={"encoding": "utf-8"},
            )
            documents.extend(txt_loader.load())

        # Load .pdf
        for pdf_file in sorted(docs_path.glob("**/*.pdf")):
            try:
                docs = PyPDFLoader(str(pdf_file)).load()
                documents.extend(docs)
                logger.info(f"Đã load PDF: {pdf_file.name} ({len(docs)} trang)")
            except Exception as e:
                logger.warning(f"Không load được PDF {pdf_file.name}: {e}")

        if not documents:
            logger.warning("Không load được tài liệu nào")
            return 0

        loaded_names = sorted({Path(d.metadata.get("source", "")).name for d in documents if d.metadata.get("source")})
        logger.info(f"Đã load {len(documents)} doc từ {len(loaded_names)} file: {', '.join(loaded_names[:10])}{'...' if len(loaded_names) > 10 else ''}")

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        chunks = splitter.split_documents(documents)

        self._vectorstore = Chroma.from_documents(
            documents=chunks,
            embedding=self._get_embeddings(),
            persist_directory=self._persist_dir,
        )

        logger.info(f"Indexed {len(chunks)} chunks from {len(documents)} documents")
        return len(chunks)

    def retrieve(self, query: str, k: int = 3) -> str:
        """Truy xuất context liên quan từ knowledge base."""
        if not self._ensure_enabled():
            return ""
        vectorstore = self._get_vectorstore()
        if vectorstore is None:
            return ""
        try:
            results = vectorstore.similarity_search(query, k=k)
        except Exception as e:
            logger.warning("RAG similarity_search lỗi, bỏ qua context: {}", e)
            return ""
        if not results:
            return ""

        context = "\n\n---\n\n".join(
            f"[Nguồn: {doc.metadata.get('source', 'N/A')}]\n{doc.page_content}"
            for doc in results
        )
        return context

    def retrieve_with_scores(self, query: str, k: int = 5) -> list[tuple]:
        """Truy xuất kèm điểm similarity, lọc theo threshold."""
        if not self._ensure_enabled():
            return []
        vectorstore = self._get_vectorstore()
        if vectorstore is None:
            return []
        try:
            results = vectorstore.similarity_search_with_score(query, k=k)
        except Exception as e:
            logger.warning("RAG similarity_search_with_score lỗi, trả về rỗng: {}", e)
            return []
        filtered = [
            (doc, score) for doc, score in results
            if score <= self.SCORE_THRESHOLD
        ]
        return filtered

    def retrieve_mmr(self, query: str, k: int = 3, fetch_k: int = 10, lambda_mult: float = 0.7) -> str:
        """Truy xuất dùng MMR (Maximal Marginal Relevance) để tăng đa dạng kết quả."""
        if not self._ensure_enabled():
            return ""
        vectorstore = self._get_vectorstore()
        if vectorstore is None:
            return ""
        try:
            results = vectorstore.max_marginal_relevance_search(
                query, k=k, fetch_k=fetch_k, lambda_mult=lambda_mult,
            )
        except Exception as e:
            logger.warning("RAG MMR lỗi, bỏ qua context: {}", e)
            return ""
        if not results:
            return ""

        context = "\n\n---\n\n".join(
            f"[Nguồn: {doc.metadata.get('source', 'N/A')}]\n{doc.page_content}"
            for doc in results
        )
        return context

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
    from langchain_community.embeddings import HuggingFaceEmbeddings
    from langchain_community.vectorstores import Chroma
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_community.document_loaders import DirectoryLoader, TextLoader

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
