"""Jev (TypeSafe AI): format request, kiểm tra đáp án -> vòng tự sửa, RAG gate, fail-open."""

import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.models.schemas import ExamType, Level, Skill, ToeicReadingPart
from app.services.jev_service import MCQVerdict, jev_service
from app.services.llm_service import llm_service
from app.services.rag_service import rag_service


def _q(ans="B"):
    return {"content": "The manager ___ the report.",
            "options": ["A. review", "B. reviewed", "C. reviewing", "D. reviews"], "correct_answer": ans}


@pytest.fixture
def jev_on(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "ts-test")
    get_settings.cache_clear()
    calls = []

    def install(handler):
        def wrapped(request: httpx.Request):
            calls.append({"headers": dict(request.headers), "body": json.loads(request.content)})
            return handler(calls[-1]["body"])

        jev_service._client = httpx.AsyncClient(
            base_url="https://api.typesafe.ai/v1",
            headers={"Authorization": "Bearer ts-test"},
            transport=httpx.MockTransport(wrapped),
        )
        return calls

    yield install
    jev_service._client = None
    get_settings.cache_clear()


def _answers(**ans):
    return httpx.Response(200, json={"model": "jev-1.13.0", "answers": ans})


@pytest.fixture
def fake_llm(monkeypatch):
    outputs, sent = [], []

    class Comp:
        async def create(self, **kw):
            sent.append(kw)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=outputs.pop(0)))],
                usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
            )

    monkeypatch.setattr(llm_service, "_client", SimpleNamespace(chat=SimpleNamespace(completions=Comp())))
    monkeypatch.setattr(type(llm_service), "_use_finetuned", property(lambda self: False))
    return outputs, sent


# ---------------- request / parsing ----------------
@pytest.mark.asyncio
async def test_verify_request_format(jev_on):
    calls = jev_on(lambda body: _answers(q0={"choice": "B", "confidence": 0.93}))
    v = await jev_service.verify_questions([("", "The manager ___ the report.", _q()["options"], "B")])
    assert v == [MCQVerdict(0, "B", "B", 0.93)]
    body = calls[0]["body"]
    assert calls[0]["headers"]["authorization"] == "Bearer ts-test"
    assert body["model"] == "jev-latest"
    q0 = body["questions"]["q0"]
    assert q0["type"] == "choice"
    assert q0["criteria"]["B"] == {"what": "reviewed"}  # bỏ tiền tố "B. "
    assert set(q0["criteria"]) == {"A", "B", "C", "D"}


def test_disagreement_threshold():
    vs = [MCQVerdict(0, "B", "C", 0.95), MCQVerdict(1, "A", "C", 0.5), MCQVerdict(2, "D", "D", 0.99)]
    errs = jev_service.disagreement_errors(vs)
    assert len(errs) == 1 and "Câu 1" in errs[0] and "chọn C" in errs[0]


# ---------------- tích hợp với sinh đề ----------------
@pytest.mark.asyncio
async def test_generation_repairs_when_jev_disagrees(jev_on, fake_llm):
    outputs, sent = fake_llm
    outputs += [json.dumps({"questions": [_q("A")]}), json.dumps({"questions": [_q("B")]})]
    jev_on(lambda body: _answers(q0={"choice": "B", "confidence": 0.95}))
    out = await llm_service.generate_questions(
        ExamType.TOEIC, Skill.READING, Level.INTERMEDIATE, 1, ToeicReadingPart.PART5
    )
    assert out[0]["correct_answer"] == "B"
    assert len(sent) == 2
    assert "kiểm tra độc lập chọn B" in sent[1]["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_generation_fail_open_when_jev_errors(jev_on, fake_llm):
    outputs, sent = fake_llm
    outputs.append(json.dumps({"questions": [_q("A")]}))
    jev_on(lambda body: httpx.Response(500, json={"error": "boom"}))
    out = await llm_service.generate_questions(
        ExamType.TOEIC, Skill.READING, Level.INTERMEDIATE, 1, ToeicReadingPart.PART5
    )
    assert out[0]["correct_answer"] == "A" and len(sent) == 1


@pytest.mark.asyncio
async def test_no_key_means_no_jev():
    get_settings.cache_clear()
    assert not jev_service.enabled
    assert llm_service._jev_verifier(1) is None
    assert await jev_service.needs_rag("xin chào") is True


# ---------------- RAG gate trong /chat ----------------
def test_chat_skips_rag_for_greeting(jev_on, monkeypatch):
    jev_on(lambda body: _answers(needs_reference={"noul": 0.05}))
    retrieved = []
    monkeypatch.setattr(rag_service, "retrieve_mmr", lambda *a, **k: retrieved.append(a) or "")
    contexts = []

    async def fake_chat(message, history, rag_context="", *, llm_provider=None):
        contexts.append(rag_context)
        return "Chào bạn!"

    monkeypatch.setattr(llm_service, "chat", fake_chat)
    with TestClient(app) as c:
        r = c.post("/api/v1/chat", json={"message": "xin chào"})
    assert r.status_code == 200
    assert retrieved == [] and contexts == [""]


def test_chat_uses_rag_for_grammar_question(jev_on, monkeypatch):
    jev_on(lambda body: _answers(needs_reference={"noul": 0.92}))
    retrieved = []
    monkeypatch.setattr(rag_service, "retrieve_mmr",
                        lambda *a, **k: retrieved.append(a) or "[Nguồn: grammar.txt]\nsince + mốc")

    async def fake_chat(message, history, rag_context="", *, llm_provider=None):
        return "since + mốc thời gian"

    monkeypatch.setattr(llm_service, "chat", fake_chat)
    with TestClient(app) as c:
        r = c.post("/api/v1/chat", json={"message": "since và for khác nhau?"})
    assert r.status_code == 200
    assert len(retrieved) == 1 and r.json()["sources"] == ["grammar.txt"]
