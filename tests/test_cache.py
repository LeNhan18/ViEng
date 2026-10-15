"""Cache trong RAM khi không có Redis."""

import pytest

from app.services import cache_service as cs


@pytest.mark.asyncio
async def test_memory_fallback_roundtrip_and_ttl(monkeypatch):
    svc = cs.CacheService()
    monkeypatch.setattr(svc, "_redis", lambda: None)
    key = cs.make_key("t", "a", 1)
    assert await svc.get_json("t", key) is None
    await svc.set_json(key, {"x": "ý"}, ttl=60)
    assert await svc.get_json("t", key) == {"x": "ý"}
    await svc.set_bytes(key + "b", b"\x00\x01", ttl=60)
    assert await svc.get_bytes("t", key + "b") == b"\x00\x01"
    await svc.set_text(key + "e", "v", ttl=-1)  # đã hết hạn
    assert await svc.get_text("t", key + "e") is None


def test_lru_evicts_oldest():
    lru = cs._MemoryLRU(2)
    lru.set("a", "1", 60)
    lru.set("b", "2", 60)
    lru.get("a")
    lru.set("c", "3", 60)
    assert lru.get("b") is None and lru.get("a") == "1" and lru.get("c") == "3"


def test_key_depends_on_all_parts():
    assert cs.make_key("n", "a", "b") != cs.make_key("n", "a", "c")
    assert cs.make_key("n", "a") == cs.make_key("n", "a")
