"""Cache kết quả tốn kém (TTS, dịch): Redis khi bật, nếu không dùng LRU trong RAM.

Key = sha256 của các tham số ảnh hưởng tới kết quả (kể cả model), nên đổi model/giọng
sẽ không trả nhầm kết quả cũ. Cache lỗi không bao giờ làm hỏng request.
"""

from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
from collections import OrderedDict

from loguru import logger

from app.core.config import get_settings
from app.core.observability import stats


def make_key(namespace: str, *parts) -> str:
    raw = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return f"vieng:cache:{namespace}:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"


class _MemoryLRU:
    def __init__(self, max_items: int):
        self._max = max_items
        self._data: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> str | None:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            expires, value = item
            if expires < time.time():
                self._data.pop(key, None)
                return None
            self._data.move_to_end(key)
            return value

    def set(self, key: str, value: str, ttl: int) -> None:
        with self._lock:
            self._data[key] = (time.time() + ttl, value)
            self._data.move_to_end(key)
            while len(self._data) > self._max:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


class CacheService:
    def __init__(self) -> None:
        self._memory = _MemoryLRU(get_settings().cache_memory_items)

    @property
    def enabled(self) -> bool:
        return get_settings().cache_enabled

    def _redis(self):
        from app.services.chat_memory_service import chat_memory_service

        return chat_memory_service.get_redis_client()

    def _record(self, namespace: str, hit: bool) -> None:
        stats.record("cache", f"{namespace}:{'hit' if hit else 'miss'}", 0.0)

    async def get_text(self, namespace: str, key: str) -> str | None:
        if not self.enabled:
            return None
        value = None
        use_memory = True
        r = self._redis()
        if r is not None:
            try:
                value = await r.get(key)
                use_memory = False  # Redis là nguồn chuẩn khi đang hoạt động
            except Exception as e:  # noqa: BLE001
                logger.warning("Cache Redis get lỗi: {}", e)
        if use_memory:
            value = self._memory.get(key)
        self._record(namespace, value is not None)
        return value

    async def set_text(self, key: str, value: str, ttl: int) -> None:
        if not self.enabled:
            return
        r = self._redis()
        if r is not None:
            try:
                await r.set(key, value, ex=ttl)
                return
            except Exception as e:  # noqa: BLE001
                logger.warning("Cache Redis set lỗi: {}", e)
        self._memory.set(key, value, ttl)

    async def get_json(self, namespace: str, key: str):
        raw = await self.get_text(namespace, key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return None

    async def set_json(self, key: str, value, ttl: int) -> None:
        await self.set_text(key, json.dumps(value, ensure_ascii=False), ttl)

    async def get_bytes(self, namespace: str, key: str) -> bytes | None:
        raw = await self.get_text(namespace, key)
        return base64.b64decode(raw) if raw is not None else None

    async def set_bytes(self, key: str, value: bytes, ttl: int) -> None:
        await self.set_text(key, base64.b64encode(value).decode("ascii"), ttl)


cache_service = CacheService()
