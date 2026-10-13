"""Gọi LLM cho eval (solver/judge). Dùng chung OpenRouter client của llm_service
nhưng cho phép chọn model riêng qua EVAL_SOLVER_MODEL / EVAL_JUDGE_MODEL.

Khuyến nghị: dùng judge/solver khác họ với LLM_MODEL để giảm thiên vị tự chấm.
"""

from __future__ import annotations

import asyncio
import os
import re

from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.services.llm_service import llm_service
from app.services.structured import coerce_to_schema, extract_json

_SEM = asyncio.Semaphore(int(os.getenv("EVAL_CONCURRENCY", "5")))


def solver_model() -> str:
    return os.getenv("EVAL_SOLVER_MODEL") or get_settings().llm_model


def judge_model() -> str:
    return os.getenv("EVAL_JUDGE_MODEL") or get_settings().llm_model


def _client():
    client = llm_service._openrouter_client
    if client is None:
        raise RuntimeError("Eval cần OPENROUTER_API_KEY.")
    return client


async def ask_text(model: str, system: str, prompt: str, *, max_tokens: int = 400) -> str:
    async with _SEM:
        resp = await _client().chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=max_tokens,
        )
    return resp.choices[0].message.content or ""


async def ask_json(model: str, system: str, prompt: str, schema: type[BaseModel], *, retries: int = 1):
    last_err = None
    for _ in range(retries + 1):
        raw = await ask_text(model, system, prompt + "\n\nChỉ trả về JSON.", max_tokens=600)
        try:
            return coerce_to_schema(extract_json(raw), schema)
        except (ValueError, ValidationError) as e:
            last_err = e
    raise RuntimeError(f"Judge trả về JSON không hợp lệ: {last_err}")


_LETTER = re.compile(r"\b([ABCD])\b")


def parse_letter(text: str) -> str | None:
    """Lấy đáp án A-D từ câu trả lời của solver ('Answer: B', '(C)', 'B. reviewed'...)."""
    t = (text or "").strip().upper()
    m = re.search(r"ANSWER\s*[:\-]?\s*\(?([ABCD])\b", t)
    if m:
        return m.group(1)
    m = _LETTER.search(t)
    return m.group(1) if m else None
