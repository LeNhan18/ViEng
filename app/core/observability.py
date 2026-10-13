"""Observability nhẹ cho ViEng: đo từng lời gọi LLM và từng HTTP request.

- Mỗi lời gọi LLM ghi 1 dòng log có cấu trúc (task, model, latency, tokens,
  số lần tự sửa, lỗi) và cộng dồn vào bộ thống kê trong RAM.
- GET /api/v1/metrics trả p50/p95 latency, tỉ lệ lỗi, token theo task/route.
- Nếu đặt LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY và cài `langfuse`, client
  OpenAI được thay bằng bản drop-in của Langfuse để trace đầy đủ prompt/response.
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from loguru import logger

_WINDOW = 500  # số mẫu gần nhất giữ lại cho mỗi key


@dataclass
class _Series:
    latencies_ms: deque = field(default_factory=lambda: deque(maxlen=_WINDOW))
    count: int = 0
    errors: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    repairs: int = 0


class _Stats:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, dict[str, _Series]] = defaultdict(lambda: defaultdict(_Series))

    def record(
        self,
        group: str,
        key: str,
        latency_ms: float,
        *,
        error: bool = False,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        repairs: int = 0,
    ) -> None:
        with self._lock:
            s = self._data[group][key]
            s.count += 1
            s.errors += int(error)
            s.latencies_ms.append(latency_ms)
            s.prompt_tokens += prompt_tokens
            s.completion_tokens += completion_tokens
            s.repairs += repairs

    @staticmethod
    def _pct(values: list[float], p: float) -> float:
        if not values:
            return 0.0
        values = sorted(values)
        idx = min(len(values) - 1, max(0, round(p / 100 * (len(values) - 1))))
        return round(values[idx], 1)

    def snapshot(self) -> dict:
        with self._lock:
            out: dict = {}
            for group, series in self._data.items():
                out[group] = {}
                for key, s in series.items():
                    lat = list(s.latencies_ms)
                    out[group][key] = {
                        "count": s.count,
                        "errors": s.errors,
                        "error_rate": round(s.errors / s.count, 3) if s.count else 0.0,
                        "p50_ms": self._pct(lat, 50),
                        "p95_ms": self._pct(lat, 95),
                        "prompt_tokens": s.prompt_tokens,
                        "completion_tokens": s.completion_tokens,
                        "repairs": s.repairs,
                    }
            return out

    def reset(self) -> None:
        with self._lock:
            self._data.clear()


stats = _Stats()


class LLMSpan:
    """Thông tin do caller điền trong lúc gọi LLM."""

    def __init__(self, task: str, model: str):
        self.task = task
        self.model = model
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.repairs = 0

    def add_usage(self, usage) -> None:
        if usage is None:
            return
        self.prompt_tokens += int(getattr(usage, "prompt_tokens", 0) or 0)
        self.completion_tokens += int(getattr(usage, "completion_tokens", 0) or 0)


@asynccontextmanager
async def llm_span(task: str, model: str):
    span = LLMSpan(task, model)
    t0 = time.perf_counter()
    error: Exception | None = None
    try:
        yield span
    except Exception as e:  # noqa: BLE001 - ghi nhận rồi ném lại
        error = e
        raise
    finally:
        ms = (time.perf_counter() - t0) * 1000
        stats.record(
            "llm",
            task,
            ms,
            error=error is not None,
            prompt_tokens=span.prompt_tokens,
            completion_tokens=span.completion_tokens,
            repairs=span.repairs,
        )
        logger.bind(event="llm_call").info(
            "llm task={} model={} latency_ms={:.0f} prompt_tokens={} completion_tokens={} "
            "repairs={} error={}",
            task,
            model,
            ms,
            span.prompt_tokens,
            span.completion_tokens,
            span.repairs,
            type(error).__name__ if error else "-",
        )


def make_async_openai_client(**kwargs):
    """Trả về AsyncOpenAI; dùng bản drop-in của Langfuse nếu được cấu hình."""
    from app.core.config import get_settings

    s = get_settings()
    if s.langfuse_public_key and s.langfuse_secret_key:
        os.environ.setdefault("LANGFUSE_PUBLIC_KEY", s.langfuse_public_key)
        os.environ.setdefault("LANGFUSE_SECRET_KEY", s.langfuse_secret_key)
        if s.langfuse_host:
            os.environ.setdefault("LANGFUSE_HOST", s.langfuse_host)
        try:
            from langfuse.openai import AsyncOpenAI  # type: ignore

            logger.info("Langfuse tracing enabled ({})", s.langfuse_host or "cloud")
            return AsyncOpenAI(**kwargs)
        except Exception as e:  # noqa: BLE001
            logger.warning("Không bật được Langfuse ({}); dùng OpenAI client thường.", e)

    from openai import AsyncOpenAI

    return AsyncOpenAI(**kwargs)
