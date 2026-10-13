"""Test structured outputs: validate + self-repair + metrics, dùng LLM client giả."""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.observability import stats
from app.main import app
from app.models.schemas import ExamType, Level, Skill, ToeicReadingPart
from app.services.llm_service import llm_service
from app.services.structured import (
    QuestionSet,
    StructuredOutputError,
    extract_json,
    normalize_options,
    validate_part6,
    validate_question_set,
    Part6Set,
)


def _q(content="The manager ___ the report.", opts=None, ans="B"):
    return {
        "content": content,
        "options": opts or ["A. review", "B. reviewed", "C. reviewing", "D. reviews"],
        "correct_answer": ans,
    }


class FakeCompletions:
    """Trả lần lượt các output đã định sẵn; ghi lại messages mỗi lần gọi."""

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    async def create(self, *, model, messages, **kw):
        self.calls.append([dict(m) for m in messages])
        content = self.outputs.pop(0)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
        )


class FakeClient:
    """Không có .parse -> llm_service dùng JSON text mode."""

    def __init__(self, outputs):
        self.chat = SimpleNamespace(completions=FakeCompletions(outputs))


@pytest.fixture
def fake_llm(monkeypatch):
    def install(outputs):
        client = FakeClient(outputs)
        monkeypatch.setattr(llm_service, "_openrouter_client", client)
        monkeypatch.setattr(type(llm_service), "_use_finetuned", property(lambda self: False))
        return client.chat.completions

    stats.reset()
    return install


# ---------------- unit: helpers ----------------
def test_extract_json_handles_fences_and_preamble():
    assert extract_json('```json\n[{"a": 1}]\n```') == [{"a": 1}]
    assert extract_json('Đây là kết quả:\n{"a": 1}\nHết.') == {"a": 1}


def test_normalize_options_adds_prefix():
    assert normalize_options(["review", "(b) reviewed", "C) x", "d: y"]) == [
        "A. review", "B. reviewed", "C. x", "D. y",
    ]


def test_validate_question_set_detects_errors():
    obj = QuestionSet.model_validate({"questions": [_q(opts=["A. a", "B. a", "C. c"]), _q(content="No blank")]})
    errs = validate_question_set(obj, 3, require_blank=True)
    joined = " | ".join(errs)
    assert "Cần 3 câu hỏi" in joined
    assert "4 đáp án" in joined
    assert "trùng" in joined
    assert "chỗ trống" in joined


def test_validate_part6_requires_four_questions():
    obj = Part6Set.model_validate({"passages": [{"passage": "word " * 60, "questions": [_q()] * 3}]})
    assert any("4 câu hỏi" in e for e in validate_part6(obj, 1))


# ---------------- integration: repair loop ----------------
@pytest.mark.asyncio
async def test_generate_part5_valid_first_try(fake_llm):
    calls = fake_llm([json.dumps([_q(), _q()])])
    out = await llm_service.generate_questions(
        ExamType.TOEIC, Skill.READING, Level.INTERMEDIATE, 2, ToeicReadingPart.PART5
    )
    assert [q["id"] for q in out] == [1, 2]
    assert len(calls.calls) == 1
    snap = stats.snapshot()["llm"]["generate_part5"]
    assert snap["count"] == 1 and snap["repairs"] == 0 and snap["prompt_tokens"] == 100


@pytest.mark.asyncio
async def test_generate_part5_self_repairs(fake_llm):
    bad = json.dumps([_q(opts=["A. x", "B. y", "C. z"])])
    good = json.dumps({"questions": [_q()]})
    calls = fake_llm([bad, good])
    out = await llm_service.generate_questions(
        ExamType.TOEIC, Skill.READING, Level.INTERMEDIATE, 1, ToeicReadingPart.PART5
    )
    assert out[0]["options"][0] == "A. review"
    assert len(calls.calls) == 2
    repair_msg = calls.calls[1][-1]["content"]
    assert "4 đáp án" in repair_msg
    assert stats.snapshot()["llm"]["generate_part5"]["repairs"] == 1


@pytest.mark.asyncio
async def test_generate_gives_up_after_max_repairs(fake_llm):
    fake_llm(["not json"] * 5)
    with pytest.raises(StructuredOutputError):
        await llm_service.generate_questions(
            ExamType.TOEIC, Skill.READING, Level.INTERMEDIATE, 1, ToeicReadingPart.PART5
        )
    snap = stats.snapshot()["llm"]["generate_part5"]
    assert snap["errors"] == 1 and snap["repairs"] == 2


def test_generate_endpoint_returns_502_on_invalid_output(fake_llm):
    fake_llm(["oops"] * 5)
    with TestClient(app) as c:
        r = c.post(
            "/api/v1/test/generate",
            json={"exam_type": "toeic", "skill": "reading", "level": "intermediate",
                  "num_questions": 1, "part": "part5"},
        )
    assert r.status_code == 502


def test_translate_structured_and_metrics_endpoint(fake_llm):
    fake_llm([json.dumps({"translated": "Xin chào", "vocabulary": [
        {"word": "hello", "meaning": "xin chào", "example": "Hello!"}], "grammar_notes": []})])
    with TestClient(app) as c:
        r = c.post("/api/v1/translate", json={"text": "Hello", "direction": "en_to_vi", "level": "beginner"})
        assert r.status_code == 200
        assert r.json()["translated"] == "Xin chào"
        assert "X-Process-Time-ms" in r.headers
        m = c.get("/api/v1/metrics").json()
    assert m["llm"]["translate"]["count"] == 1
    assert m["http"]["POST /api/v1/translate"]["count"] == 1
