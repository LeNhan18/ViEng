from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import DirectoryLoader, TextLoader
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

    def _get_embeddings(self):
        if self._embeddings is None:
            self._embeddings = HuggingFaceEmbeddings(
                model_name=self._embedding_model,
                model_kwargs={"device": "cpu"},
            )
        return self._embeddings

    def _get_vectorstore(self):
        if self._vectorstore is None:
            persist_path = Path(self._persist_dir)
            if persist_path.exists() and any(persist_path.iterdir()):
                self._vectorstore = Chroma(
                    persist_directory=self._persist_dir,
                    embedding_function=self._get_embeddings(),
                )
                logger.info(f"Loaded vectorstore from {self._persist_dir}")
            else:
                logger.warning("Vectorstore chưa được tạo. Hãy chạy index_knowledge_base() trước.")
                return None
        return self._vectorstore

    def index_knowledge_base(self, docs_dir: str = "data/knowledge_base") -> int:
        """Đọc tài liệu từ thư mục, chia chunks, tạo embeddings và lưu vào ChromaDB."""
        docs_path = Path(docs_dir)
        if not docs_path.exists() or not any(docs_path.glob("*.txt")):
            logger.warning(f"Không tìm thấy tài liệu .txt trong {docs_dir}")
            return 0

        loader = DirectoryLoader(
            docs_dir,
            glob="**/*.txt",
            loader_cls=TextLoader,
            loader_kwargs={"encoding": "utf-8"},
        )
        documents = loader.load()

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
        vectorstore = self._get_vectorstore()
        if vectorstore is None:
            return ""

        results = vectorstore.similarity_search(query, k=k)
        if not results:
            return ""

        context = "\n\n---\n\n".join(
            f"[Nguồn: {doc.metadata.get('source', 'N/A')}]\n{doc.page_content}"
            for doc in results
        )
        return context

    def retrieve_with_scores(self, query: str, k: int = 5) -> list[tuple]:
        """Truy xuất kèm điểm similarity, lọc theo threshold."""
        vectorstore = self._get_vectorstore()
        if vectorstore is None:
            return []

        results = vectorstore.similarity_search_with_score(query, k=k)
        filtered = [
            (doc, score) for doc, score in results
            if score <= self.SCORE_THRESHOLD
        ]
        return filtered

    def retrieve_mmr(self, query: str, k: int = 3, fetch_k: int = 10, lambda_mult: float = 0.7) -> str:
        """Truy xuất dùng MMR (Maximal Marginal Relevance) để tăng đa dạng kết quả."""
        vectorstore = self._get_vectorstore()
        if vectorstore is None:
            return ""

        results = vectorstore.max_marginal_relevance_search(
            query, k=k, fetch_k=fetch_k, lambda_mult=lambda_mult,
        )
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
