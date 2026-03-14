from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.api.routes import router
from loguru import logger
import sys

settings = get_settings()

logger.remove()
logger.add(sys.stderr, level=settings.log_level.upper())
logger.add("logs/vieng.log", rotation="10 MB", retention="7 days", level="DEBUG")

app = FastAPI(
    title="ViEng API",
    description="API hỗ trợ sinh viên Việt Nam luyện thi TOEIC/IELTS với AI",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.on_event("startup")
async def startup_event():
    from app.services.rag_service import rag_service
    from pathlib import Path

    persist_path = Path(settings.chroma_persist_dir)
    if not persist_path.exists() or not any(persist_path.iterdir()):
        logger.info("Vectorstore chưa có, đang index knowledge base...")
        count = rag_service.index_knowledge_base()
        if count > 0:
            logger.info(f"Đã index {count} chunks khi khởi động")
        else:
            logger.warning("Không có tài liệu trong data/knowledge_base/ để index")
    else:
        logger.info("Vectorstore đã tồn tại, bỏ qua index")


@app.get("/")
async def root():
    return {
        "app": "ViEng",
        "version": "0.1.0",
        "docs": "/docs",
        "message": "Chào mừng đến với ViEng - Trợ lý luyện thi tiếng Anh AI",
    }
