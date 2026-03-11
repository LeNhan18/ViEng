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


@app.get("/")
async def root():
    return {
        "app": "ViEng",
        "version": "0.1.0",
        "docs": "/docs",
        "message": "Chào mừng đến với ViEng - Trợ lý luyện thi tiếng Anh AI",
    }
