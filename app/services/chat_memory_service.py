import json
from datetime import datetime
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.core.config import get_settings
from app.models.orm import ChatMessage as ChatMessageORM


class ChatMemoryService:
    def __init__(self):
        self.settings = get_settings()
        self._redis_client = None

    def get_redis_client(self):
        if not self.settings.use_redis:
            return None
        if self._redis_client is None:
            try:
                # Tạo connection pool và client
                self._redis_client = aioredis.Redis(
                    host=self.settings.redis_host,
                    port=self.settings.redis_port,
                    password=self.settings.redis_password or None,
                    db=self.settings.redis_db,
                    decode_responses=True,
                    socket_timeout=2.0,
                    socket_connect_timeout=2.0,
                )
                logger.info(
                    f"Initialized Redis client: {self.settings.redis_host}:{self.settings.redis_port}"
                )
            except Exception as e:
                logger.error(f"Failed to initialize Redis client: {e}")
        return self._redis_client

    async def get_history(self, user_id: int, db: AsyncSession | None = None) -> list[dict]:
        """Lấy lịch sử chat của user. Ưu tiên Redis, fallback sang Database."""
        # 1. Thử lấy từ Redis
        redis_client = self.get_redis_client()
        if redis_client:
            try:
                key = f"vieng:chat_history:{user_id}"
                messages_raw = await redis_client.lrange(key, 0, -1)
                if messages_raw:
                    history = []
                    for msg in messages_raw:
                        try:
                            history.append(json.loads(msg))
                        except Exception:
                            continue
                    return history
            except Exception as e:
                logger.warning(f"Error reading chat history from Redis: {e}. Falling back to DB.")

        # 2. Thử lấy từ Database nếu Redis không có hoặc lỗi
        if db and self.settings.use_database:
            try:
                stmt = (
                    select(ChatMessageORM)
                    .where(ChatMessageORM.user_id == user_id)
                    .order_by(ChatMessageORM.created_at.asc())
                )
                result = await db.execute(stmt)
                db_messages = result.scalars().all()

                history = []
                for msg in db_messages:
                    try:
                        sources = json.loads(msg.sources) if msg.sources else []
                    except Exception:
                        sources = []
                    history.append({
                        "role": msg.role,
                        "content": msg.content,
                        "sources": sources,
                    })

                # Nếu Redis được bật nhưng trống, đồng bộ lại dữ liệu từ DB sang Redis để tối ưu cho lần sau
                if redis_client and history:
                    try:
                        key = f"vieng:chat_history:{user_id}"
                        await redis_client.delete(key)
                        for msg in history:
                            await redis_client.rpush(key, json.dumps(msg))
                        await redis_client.expire(key, 30 * 24 * 3600)  # Hết hạn sau 30 ngày
                    except Exception as re:
                        logger.warning(f"Error syncing history to Redis: {re}")

                return history
            except Exception as e:
                logger.error(f"Error reading chat history from Database: {e}")

        return []

    async def add_message(
        self,
        user_id: int,
        role: str,
        content: str,
        sources: list[str] | None = None,
        db: AsyncSession | None = None,
    ):
        """Lưu tin nhắn mới vào Redis và Database."""
        msg_dict = {
            "role": role,
            "content": content,
            "sources": sources or [],
            "created_at": datetime.utcnow().isoformat(),
        }

        # 1. Lưu vào Redis
        redis_client = self.get_redis_client()
        if redis_client:
            try:
                key = f"vieng:chat_history:{user_id}"
                await redis_client.rpush(key, json.dumps(msg_dict))
                # Giới hạn số lượng tin nhắn trong cache Redis để tránh phình bộ nhớ (tối đa 100 tin gần nhất)
                await redis_client.ltrim(key, -100, -1)
                await redis_client.expire(key, 30 * 24 * 3600)
            except Exception as e:
                logger.warning(f"Error saving chat message to Redis: {e}")

        # 2. Lưu vào Database
        if db and self.settings.use_database:
            try:
                sources_str = json.dumps(sources) if sources else None
                db_msg = ChatMessageORM(
                    user_id=user_id,
                    role=role,
                    content=content,
                    sources=sources_str,
                    created_at=datetime.utcnow(),
                )
                db.add(db_msg)
                await db.commit()
            except Exception as e:
                logger.error(f"Error saving chat message to Database: {e}")
                try:
                    await db.rollback()
                except Exception:
                    pass

    async def clear_history(self, user_id: int, db: AsyncSession | None = None):
        """Xóa lịch sử chat của user trong cả Redis và Database."""
        # 1. Xóa trong Redis
        redis_client = self.get_redis_client()
        if redis_client:
            try:
                key = f"vieng:chat_history:{user_id}"
                await redis_client.delete(key)
            except Exception as e:
                logger.warning(f"Error clearing chat history in Redis: {e}")

        # 2. Xóa trong Database
        if db and self.settings.use_database:
            try:
                from sqlalchemy import delete

                stmt = delete(ChatMessageORM).where(ChatMessageORM.user_id == user_id)
                await db.execute(stmt)
                await db.commit()
            except Exception as e:
                logger.error(f"Error clearing chat history in Database: {e}")
                try:
                    await db.rollback()
                except Exception:
                    pass


chat_memory_service = ChatMemoryService()
