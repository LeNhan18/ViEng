from functools import lru_cache
from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import os
load_dotenv()
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "info"

    # Pydantic BaseSettings tự động đọc từ .env, chỉ cần khai báo kiểu dữ liệu.
    # Đảm bảo trong file .env bạn đặt tên biến là OPENROUTER_API_KEY
    openrouter_api_key: str = ""
    # LLM provider:
    # - "auto": ưu tiên Claude (ANTHROPIC_API_KEY) -> OpenRouter; USE_FINETUNED_MODEL=true thì dùng HF
    # - "anthropic" | "openrouter" | "hf_inference" | "hf_local"
    llm_provider: str = "auto"
    # Model OpenRouter mặc định cho mọi tác vụ.
    llm_model: str = "openai/gpt-4o-mini"

    # Claude API (Anthropic) qua endpoint tương thích OpenAI.
    # LLM_PROVIDER=auto sẽ ưu tiên Claude khi có ANTHROPIC_API_KEY.
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-5-5"
    anthropic_base_url: str = "https://api.anthropic.com/v1/"
    # Jev (TypeSafe AI) - model ra quyết định, tuỳ chọn. Trống key = tắt.
    typesafe_api_key: str = ""
    jev_model: str = "jev-latest"
    jev_base_url: str = "https://api.typesafe.ai/v1"
    jev_timeout_s: float = 8.0
    # Kiểm tra đáp án đề do LLM sinh: Jev chọn khác đáp án với độ tin cậy >= ngưỡng -> bắt LLM sửa.
    jev_verify_questions: bool = True
    jev_verify_threshold: float = 0.8
    # Bỏ qua RAG cho tin nhắn không cần tra cứu (chào hỏi...) khi P(cần tra cứu) < ngưỡng.
    jev_rag_gate: bool = True
    jev_rag_threshold: float = 0.3
    # Cache kết quả TTS/dịch (Redis nếu USE_REDIS, nếu không thì RAM)
    cache_enabled: bool = True
    cache_memory_items: int = 512
    tts_cache_ttl_s: int = 30 * 24 * 3600
    translate_cache_ttl_s: int = 7 * 24 * 3600
    tts_voice: str = "en-US-AriaNeural"
    # Số lần cho LLM tự sửa khi output sai schema/nghiệp vụ.
    llm_max_repairs: int = 2

    # Observability (tuỳ chọn): Langfuse tracing
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = ""

    chroma_persist_dir: str = "./data/vectorstore"
    # Model id trên Hugging Face hoặc đường dẫn thư mục model local
    embedding_model: str = "BAAI/bge-m3"
    rag_enabled: bool = True
    # Hybrid retrieval: BM25 (từ khoá) + vector, gộp bằng Reciprocal Rank Fusion
    rag_hybrid: bool = True
    rag_fetch_k: int = 20
    # Cross-encoder rerank (tuỳ chọn, cần sentence-transformers), vd. BAAI/bge-reranker-v2-m3
    rag_reranker_model: str = ""
    rag_chunk_size: int = 500
    rag_chunk_overlap: int = 50
    # Bảo vệ /rag/index: header X-Admin-Token. Trống = chỉ cho phép khi APP_ENV != production
    admin_token: str = ""

    hf_model_name: str = ""
    use_finetuned_model: bool = False
    hf_token: str = ""

    # CORS: "*" or comma-separated origins, e.g. http://localhost:5173,http://127.0.0.1:3000
    cors_origins: str = "*"

    # If non-empty, clients must send header X-API-Key matching this value.
    api_key: str = ""

    # OCR (chat with image/PDF)
    ocr_enabled: bool = True
    ocr_max_file_size_mb: int = 10
    ocr_max_pdf_pages: int = 10
    # Thư mục file tạm khi OCR PDF (trống = thư mục tạm của hệ điều hành)
    ocr_temp_dir: str = ""
    # Thư mục cache model Paddle (trống = mặc định của Paddle). Vd: E:/AI_CACHE/paddle_ocr
    ocr_model_cache_dir: str = ""

    # Auth (JWT)
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_minutes: int = 60 * 24 * 7

    # MySQL async (aiomysql). Enable only when you need persistence.
    use_database: bool = False
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "vieng"
    # Ghi đè toàn bộ URL DB (vd. sqlite+aiosqlite:///./test.db cho test local). Trống = MySQL ở trên.
    database_url: str = ""

    # Redis/Redict memory storage
    use_redis: bool = False
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0

    @field_validator("cors_origins", mode="before")
    @classmethod
    def strip_cors(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
