"""Kiểm tra bộ eval không cần API key: dataset hợp lệ, chấm điểm và ngưỡng đúng."""

import json

import pytest

from app.services.structured import QuestionSet, validate_question_set
from evals import llm as ev
from evals import run as runner
from evals import suites
from app.services.llm_service import llm_service


# ---------------- dataset integrity ----------------
def test_part5_golden_is_valid():
    items = suites.load_jsonl("part5_golden.jsonl")
    assert len(items) >= 30
    assert len({i["id"] for i in items}) == len(items)
    qs = QuestionSet.model_validate({"questions": [
        {"content": i["content"], "options": i["options"], "correct_answer": i["correct_answer"]} for i in items
    ]})
    assert validate_question_set(qs, len(items), require_blank=True) == []
    # Đáp án đúng phải phân bố đủ A-D để solver không "đoán một chữ" vẫn đạt.
    assert {i["correct_answer"] for i in items} == {"A", "B", "C", "D"}


def test_chat_golden_is_valid():
    items = suites.load_jsonl("chat_golden.jsonl")
    assert len(items) >= 15
    assert all(i["question"].strip() and i["key_points"] for i in items)


@pytest.mark.parametrize("text,expected", [
    ("B", "B"), ("Answer: C", "C"), ("(D) reviews", "D"), ("The answer is A.", "A"), ("none", None),
])
def test_parse_letter(text, expected):
    assert ev.parse_letter(text) == expected


# ---------------- harness with fake LLMs ----------------
@pytest.fixture
def fake(monkeypatch):
    golden = {i["content"]: i["correct_answer"] for i in suites.load_jsonl("part5_golden.jsonl")}
    state = {"solver_wrong": set(), "judge_bad": False}

    async def ask_text(model, system, prompt, max_tokens=400):
        q = prompt.split("Question: ", 1)[1].split("\n", 1)[0]
        ans = golden.get(q, "A")
        return "D" if q in state["solver_wrong"] and ans != "D" else ans

    async def ask_json(model, system, prompt, schema, retries=1):
        if schema is suites.ExplainVerdict:
            ok = not state["judge_bad"]
            return schema(states_correct_answer=True, factually_correct=ok, explains_why_user_wrong=True,
                          issues=[] if ok else ["sai quy tắc"])
        n = prompt.count("\n", prompt.index("bắt buộc:"), prompt.index("Câu trả lời")) - 2
        return schema(covered=[True] * n, incorrect_claims=[])

    async def gen(*a, **k):
        part = a[4] if len(a) > 4 else k.get("part")
        q = {"id": 1, "content": "The manager ___ the report.",
             "options": ["A. review", "B. reviewed", "C. reviewing", "D. reviews"], "correct_answer": "A"}
        if part.value == "part5":
            return [q]
        if part.value == "part6":
            return [{"passage": "text", "questions": [q] * 4}]
        return [{"passages": ["text"], "questions": [q] * 2}]

    async def explain(**k):
        return "giải thích"

    async def chat(**k):
        return "trả lời"

    monkeypatch.setattr(ev, "ask_text", ask_text)
    monkeypatch.setattr(ev, "ask_json", ask_json)
    monkeypatch.setattr(llm_service, "generate_questions", gen)
    monkeypatch.setattr(llm_service, "explain_answer", explain)
    monkeypatch.setattr(llm_service, "chat", chat)
    return state


@pytest.mark.asyncio
async def test_runner_passes_with_good_models(fake, tmp_path):
    code = await runner.main(["--quick", "--out", str(tmp_path / "r.json")])
    report = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert code == 0, report
    names = {s["name"] for s in report["suites"]}
    assert names == {"solver_baseline", "generation", "explain", "chat"}
    gen = next(s for s in report["suites"] if s["name"] == "generation")
    assert gen["metrics"]["solver_agreement"] == 1.0


@pytest.mark.asyncio
async def test_runner_fails_when_quality_drops(fake, tmp_path):
    fake["judge_bad"] = True
    fake["solver_wrong"] = {"The manager ___ the report."}
    code = await runner.main(["--quick", "--out", str(tmp_path / "r.json")])
    report = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert code == 1
    failed = {(s["name"], c["metric"]) for s in report["suites"] for c in s["checks"] if not c["passed"]}
    assert ("explain", "pass_rate") in failed
    assert ("generation", "solver_agreement") in failed
    assert "## ViEng eval" in runner.to_markdown(report)
