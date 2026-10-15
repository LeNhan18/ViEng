"""Bộ nhớ chat theo user: Redis (cache 100 tin gần nhất) + DB (lưu bền vững).

- Đọc: Redis trước (chỉ lấy N tin cuối), Redis trống/lỗi -> DB (ORDER BY id DESC LIMIT)
  rồi đồng bộ lại Redis bằng 1 pipeline.
- Ghi: cả lượt (user + assistant) trong 1 pipeline Redis + 1 commit DB.
- Redis/DB lỗi không làm hỏng luồng chat (chỉ log).
"""

from __future__ import annotations

import json
from datetime import datetime

import redis.asyncio as aioredis
from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.orm import ChatMessage as ChatMessageORM

REDIS_MAX_MESSAGES = 100
REDIS_TTL_S = 30 * 24 * 3600


def _key(user_id: int) -> str:
    return f"vieng:chat_history:{user_id}"


class ChatMemoryService:
    def __init__(self):
        self.settings = get_settings()
        self._redis_client = None

    def get_redis_client(self):
        if not self.settings.use_redis:
            return None
        if self._redis_client is None:
            try:
                self._redis_client = aioredis.Redis(
                    host=self.settings.redis_host,
                    port=self.settings.redis_port,
                    password=self.settings.redis_password or None,
                    db=self.settings.redis_db,
                    decode_responses=True,
                    socket_timeout=2.0,
                    socket_connect_timeout=2.0,
                )
                logger.info(f"Initialized Redis client: {self.settings.redis_host}:{self.settings.redis_port}")
            except Exception as e:
                logger.error(f"Failed to initialize Redis client: {e}")
        return self._redis_client

    # ------------------------------------------------------------------
    # Đọc
    # ------------------------------------------------------------------
    async def get_history(
        self, user_id: int, db: AsyncSession | None = None, limit: int | None = None
    ) -> list[dict]:
        """N tin gần nhất (mặc định tối đa REDIS_MAX_MESSAGES), theo thứ tự cũ -> mới."""
        limit = min(limit or REDIS_MAX_MESSAGES, REDIS_MAX_MESSAGES)
        redis_client = self.get_redis_client()
        if redis_client:
            try:
                raw = await redis_client.lrange(_key(user_id), -limit, -1)
                if raw:
                    out = []
                    for item in raw:
                        try:
                            out.append(json.loads(item))
                        except (TypeError, ValueError):
                            continue
                    return out
            except Exception as e:
                logger.warning(f"Error reading chat history from Redis: {e}. Falling back to DB.")

        if db is None or not self.settings.use_database:
            return []
        try:
            stmt = (
                select(ChatMessageORM)
                .where(ChatMessageORM.user_id == user_id)
                .order_by(ChatMessageORM.id.desc())
                .limit(REDIS_MAX_MESSAGES)
            )
            rows = list(reversed((await db.execute(stmt)).scalars().all()))
        except Exception as e:
            logger.error(f"Error reading chat history from Database: {e}")
            return []

        history = []
        for msg in rows:
            try:
                sources = json.loads(msg.sources) if msg.sources else []
            except (TypeError, ValueError):
                sources = []
            history.append({"role": msg.role, "content": msg.content, "sources": sources})

        if redis_client and history:
            try:
                pipe = redis_client.pipeline(transaction=True)
                pipe.delete(_key(user_id))
                pipe.rpush(_key(user_id), *[json.dumps(m, ensure_ascii=False) for m in history])
                pipe.expire(_key(user_id), REDIS_TTL_S)
                await pipe.execute()
            except Exception as e:
                logger.warning(f"Error syncing history to Redis: {e}")
        return history[-limit:]

    # ------------------------------------------------------------------
    # Ghi
    # ------------------------------------------------------------------
    async def add_messages(
        self, user_id: int, messages: list[dict], db: AsyncSession | None = None
    ) -> None:
        """Lưu nhiều tin cùng lúc. messages = [{"role", "content", "sources"?}]."""
        if not messages:
            return
        now = datetime.utcnow()
        items = [
            {
                "role": m["role"],
                "content": m["content"],
                "sources": m.get("sources") or [],
                "created_at": now.isoformat(),
            }
            for m in messages
        ]

        redis_client = self.get_redis_client()
        if redis_client:
            try:
                pipe = redis_client.pipeline(transaction=True)
                pipe.rpush(_key(user_id), *[json.dumps(i, ensure_ascii=False) for i in items])
                pipe.ltrim(_key(user_id), -REDIS_MAX_MESSAGES, -1)
                pipe.expire(_key(user_id), REDIS_TTL_S)
                await pipe.execute()
            except Exception as e:
                logger.warning(f"Error saving chat messages to Redis: {e}")

        if db is not None and self.settings.use_database:
            try:
                db.add_all([
                    ChatMessageORM(
                        user_id=user_id,
                        role=i["role"],
                        content=i["content"],
                        sources=json.dumps(i["sources"], ensure_ascii=False) if i["sources"] else None,
                        created_at=now,
                    )
                    for i in items
                ])
                await db.commit()
            except Exception as e:
                logger.error(f"Error saving chat messages to Database: {e}")
                try:
                    await db.rollback()
                except Exception:
                    pass

    async def add_message(
        self,
        user_id: int,
        role: str,
        content: str,
        sources: list[str] | None = None,
        db: AsyncSession | None = None,
    ) -> None:
        """Tương thích code cũ: lưu 1 tin."""
        await self.add_messages(user_id, [{"role": role, "content": content, "sources": sources}], db=db)

    async def save_turn(
        self,
        user_id: int,
        user_content: str,
        reply: str,
        sources: list[str] | None = None,
        db: AsyncSession | None = None,
    ) -> None:
        """Lưu 1 lượt hỏi-đáp sau khi LLM trả lời thành công."""
        await self.add_messages(
            user_id,
            [
                {"role": "user", "content": user_content},
                {"role": "assistant", "content": reply, "sources": sources or []},
            ],
            db=db,
        )

    async def clear_history(self, user_id: int, db: AsyncSession | None = None):
        redis_client = self.get_redis_client()
        if redis_client:
            try:
                await redis_client.delete(_key(user_id))
            except Exception as e:
                logger.warning(f"Error clearing chat history in Redis: {e}")
        if db is not None and self.settings.use_database:
            try:
                await db.execute(delete(ChatMessageORM).where(ChatMessageORM.user_id == user_id))
                await db.commit()
            except Exception as e:
                logger.error(f"Error clearing chat history in Database: {e}")
                try:
                    await db.rollback()
                except Exception:
                    pass


chat_memory_service = ChatMemoryService()
