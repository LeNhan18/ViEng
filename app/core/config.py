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

    chroma_persist_dir: str = "./data/vectorstore"
    embedding_model: str = "sentence-transformers/models--BAAI--bge-m3"
    rag_enabled: bool = True

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
