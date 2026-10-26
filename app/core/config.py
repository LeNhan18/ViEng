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
    # - "auto": ưu tiên OpenRouter -> Groq -> OpenAI; nếu USE_FINETUNED_MODEL=true thì dùng HF (local hoặc inference)
    # - "openrouter" | "groq" | "openai" | "hf_inference" | "hf_local"
    llm_provider: str = "auto"
    # Model OpenRouter mặc định cho mọi tác vụ.
    llm_model: str = "openai/gpt-4o-mini"
    # Số lần cho LLM tự sửa khi output sai schema/nghiệp vụ.
    llm_max_repairs: int = 2

    # Observability (tuỳ chọn): Langfuse tracing
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = ""

    chroma_persist_dir: str = "./data/vectorstore"
    # ID model trên HuggingFace Hub (KHÔNG phải đường dẫn thư mục cache).
    # Trước đây mặc định là "sentence-transformers/models--BAAI--bge-m3" — đó là
    # tên thư mục trong cache HF, không phải repo id, nên không resolve được.
    embedding_model: str = "BAAI/bge-m3"
    rag_enabled: bool = True
    # Số index cũ giữ lại sau khi reindex thành công (để rollback thủ công).
    rag_keep_old_indexes: int = 1
    # Số luồng tối đa cho embedding/OCR chạy đồng thời (chống nghẽn event loop).
    rag_max_concurrency: int = 2
    # Distance metric của collection Chroma ("cosine" | "l2" | "ip").
    # Để TRỐNG = dùng mặc định của Chroma (l2) và không ghi hnsw:space, giữ nguyên
    # hành vi cũ — SCORE_THRESHOLD đang được chuẩn theo l2.
    # Đổi giá trị này thì PHẢI reindex: index cũ sẽ bị từ chối với lý do rõ ràng.
    rag_distance_metric: str = ""

    # Cache/temp dirs — để trống thì tự suy ra theo OS (xem app/core/paths.py).
    # Không hard-code ổ đĩa để chạy được cả Windows, Ubuntu và Docker.
    cache_dir: str = ""
    ocr_temp_dir: str = ""
    paddle_cache_dir: str = ""
    hf_cache_dir: str = ""

    # Khoá quản trị cho các thao tác index / xem kho tài liệu.
    # Để trống = các endpoint quản trị bị chặn hoàn toàn (fail-closed).
    admin_api_key: str = ""

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
