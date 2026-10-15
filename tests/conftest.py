import pytest

from app.services.cache_service import cache_service


@pytest.fixture(autouse=True)
def _clear_memory_cache():
    cache_service._memory.clear()
    yield
    cache_service._memory.clear()
