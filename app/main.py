from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.api.routes import router
from app.core.config import get_settings
from app.db.database import init_db

settings = get_settings()

_LOG_DIR = Path("logs")
_LOG_DIR.mkdir(parents=True, exist_ok=True)

logger.remove()
logger.add(sys.stderr, level=settings.log_level.upper())
logger.add(str(_LOG_DIR / "vieng.log"), rotation="10 MB", retention="7 days", level="DEBUG")


def _parse_cors_origins() -> tuple[list[str], bool]:
    """Return (origins, allow_credentials). Wildcard '*' disables credentials."""
    raw = (settings.cors_origins or "*").strip()
    if raw == "*":
        return ["*"], False
    origins = [x.strip() for x in raw.split(",") if x.strip()]
    if not origins:
        return ["*"], False
    return origins, True


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    from app.services.rag_service import rag_service

    # Pre-warm OCR engine ở startup để request đầu tiên không bị cold start
    # (PaddleOCR load + JIT mất ~3-5s lần đầu). Chạy nền trong threadpool để
    # không block startup; nếu OCR_ENABLED=false thì skip.
    if settings.ocr_enabled:
        import asyncio
        from fastapi.concurrency import run_in_threadpool
        from app.services.ocr_service import ocr_service

        async def _warm_ocr():
            try:
                await run_in_threadpool(ocr_service.warmup)
            except Exception as e:
                logger.warning("Pre-warm OCR failed: {}", e)

        asyncio.create_task(_warm_ocr())

    if not settings.rag_enabled:
        logger.info("RAG disabled (RAG_ENABLED=false) — skip vectorstore startup checks.")
        yield
        return

    persist_path = Path(settings.chroma_persist_dir)
    if not persist_path.exists() or not any(persist_path.iterdir()):
        logger.info("No vectorstore yet; indexing knowledge base...")
        count = rag_service.index_knowledge_base()
        if count > 0:
            logger.info(f"Indexed {count} chunks on startup")
        else:
            logger.warning("No documents in data/knowledge_base/ to index")
    else:
        logger.info("Vectorstore exists; skipping index")
    yield


class OptionalAPIKeyMiddleware(BaseHTTPMiddleware):
    """If API_KEY is set in settings, require X-API-Key header."""

    async def dispatch(self, request: Request, call_next):
        expected = (settings.api_key or "").strip()
        if not expected:
            return await call_next(request)
        path = request.url.path
        if path in ("/", "/api/v1/health"):
            return await call_next(request)
        if path.startswith("/docs") or path in ("/openapi.json", "/redoc"):
            return await call_next(request)
        if request.method == "OPTIONS":
            return await call_next(request)
        if request.headers.get("x-api-key") != expected:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key."},
            )
        return await call_next(request)


app = FastAPI(
    title="ViEng API",
    description=(
        "API h\u1ed7 tr\u1ee3 sinh vi\u00ean Vi\u1ec7t Nam luy\u1ec7n thi TOEIC/IELTS v\u1edbi AI"
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(OptionalAPIKeyMiddleware)

_cors_origins, _cors_credentials = _parse_cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_credentials,
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
        "message": (
            "Ch\u00e0o m\u1eebng \u0111\u1ebfn v\u1edbi ViEng - "
            "Tr\u1ee3 l\u00fd luy\u1ec7n thi ti\u1ebfng Anh AI"
        ),
    }
