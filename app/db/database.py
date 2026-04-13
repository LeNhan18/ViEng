"""
SQLAlchemy async engine + session factory cho MySQL.
Driver: aiomysql (URL scheme mysql+aiomysql://). Cài: pip install sqlalchemy aiomysql
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _get_db_url() -> str:
    s = get_settings()
    return (
        f"mysql+aiomysql://{s.db_user}:{s.db_password}"
        f"@{s.db_host}:{s.db_port}/{s.db_name}?charset=utf8mb4"
    )


def _create_engine() -> AsyncEngine:
    s = get_settings()
    url = _get_db_url()
    logger.info(f"DB engine: mysql+aiomysql://{s.db_user}:***@{s.db_host}:{s.db_port}/{s.db_name}")
    return create_async_engine(
        url,
        echo=False,
        pool_pre_ping=True,
        pool_recycle=3600,
        pool_size=10,
        max_overflow=20,
    )


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_engine_and_sessionmaker() -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    global _engine, _session_factory
    if _engine is None or _session_factory is None:
        _engine = _create_engine()
        _session_factory = async_sessionmaker(
            bind=_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _engine, _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    from fastapi import HTTPException

    if not get_settings().use_database:
        raise HTTPException(
            status_code=503,
            detail="Database is disabled (USE_DATABASE=false).",
        )
    _, session_factory = _get_engine_and_sessionmaker()
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Create all tables when USE_DATABASE=true."""
    settings = get_settings()
    if not settings.use_database:
        logger.info("Bo qua init_db (USE_DATABASE=false).")
        return

    from app.models import orm  # noqa: F401

    engine, _ = _get_engine_and_sessionmaker()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized OK")
