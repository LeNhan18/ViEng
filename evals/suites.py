"""Các bộ eval của ViEng.

- solver_baseline: solver làm golden Part 5 -> đo độ tin cậy của chính solver.
- generation: sinh đề thật bằng llm_service, rồi cho solver (model thứ hai) làm thử.
  Solver chọn khác đáp án đề -> câu có thể sai hoặc mơ hồ.
- explain: giải thích cho học sinh chọn sai trên golden Part 5, judge chấm đúng/sai.
- chat: chatbot trả lời câu hỏi ngữ pháp, judge chấm độ bao phủ ý chính + phát biểu sai.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

from app.core.observability import stats
from app.models.schemas import ExamType, Level, Skill, ToeicReadingPart
from app.services.llm_service import llm_service
from app.services.structured import StructuredOutputError
from evals import llm as ev

DATA = Path(__file__).parent / "datasets"


def load_jsonl(name: str) -> list[dict]:
    with open(DATA / name, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


@dataclass
class SuiteResult:
    name: str
    metrics: dict
    failures: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Solver: làm 1 câu trắc nghiệm
# ---------------------------------------------------------------------------
SOLVER_SYSTEM = (
    "You are an expert TOEIC test taker. Choose the single best answer. "
    "Reply with only the letter (A, B, C or D)."
)


def _mcq_prompt(question: str, options: list[str], context: str = "") -> str:
    ctx = f"Passage:\n{context}\n\n" if context else ""
    return f"{ctx}Question: {question}\n" + "\n".join(options) + "\nAnswer:"


async def solve(question: str, options: list[str], context: str = "") -> str | None:
    out = await ev.ask_text(ev.solver_model(), SOLVER_SYSTEM, _mcq_prompt(question, options, context), max_tokens=5)
    return ev.parse_letter(out)


# ---------------------------------------------------------------------------
# Suites
# ---------------------------------------------------------------------------
async def solver_baseline(limit: int | None = None) -> SuiteResult:
    items = load_jsonl("part5_golden.jsonl")[:limit]
    answers = await asyncio.gather(*(solve(i["content"], i["options"]) for i in items))
    failures = [
        {"id": i["id"], "expected": i["correct_answer"], "got": a, "question": i["content"]}
        for i, a in zip(items, answers)
        if a != i["correct_answer"]
    ]
    n = len(items)
    return SuiteResult("solver_baseline", {"n": n, "accuracy": round((n - len(failures)) / n, 3)}, failures)


GEN_PARTS = [
    (ToeicReadingPart.PART5, 5),
    (ToeicReadingPart.PART6, 4),
    (ToeicReadingPart.PART7_SINGLE, 3),
    (ToeicReadingPart.PART7_MULTIPLE, 5),
]


def _flatten(part: ToeicReadingPart, data: list[dict]) -> list[tuple[str, dict]]:
    """-> [(context, question_dict)]"""
    if part == ToeicReadingPart.PART5:
        return [("", q) for q in data]
    out = []
    for p in data:
        ctx = p.get("passage") or "\n\n---\n\n".join(p.get("passages", []))
        out += [(ctx, q) for q in p["questions"]]
    return out


async def generation(samples_per_part: int = 2) -> SuiteResult:
    stats.reset()
    jobs = [
        (part, n)
        for part, n in GEN_PARTS
        for _ in range(samples_per_part)
    ]

    async def run(part, n):
        try:
            return part, await llm_service.generate_questions(
                ExamType.TOEIC, Skill.READING, Level.INTERMEDIATE, n, part
            ), None
        except StructuredOutputError as e:
            return part, None, e

    results = await asyncio.gather(*(run(p, n) for p, n in jobs))

    failures: list[dict] = []
    gen_ok = 0
    to_solve: list[tuple[str, str, dict]] = []
    for part, data, err in results:
        if err is not None:
            failures.append({"part": part.value, "kind": "generation_failed", "errors": err.errors[:5]})
            continue
        gen_ok += 1
        to_solve += [(part.value, ctx, q) for ctx, q in _flatten(part, data)]

    answers = await asyncio.gather(*(solve(q["content"], q["options"], ctx) for _, ctx, q in to_solve))
    disagree = 0
    for (part, ctx, q), a in zip(to_solve, answers):
        if a != q["correct_answer"]:
            disagree += 1
            failures.append({
                "part": part, "kind": "solver_disagrees", "question": q["content"][:200],
                "options": q["options"], "key": q["correct_answer"], "solver": a,
            })

    llm = stats.snapshot().get("llm", {})
    calls = sum(v["count"] for k, v in llm.items() if k.startswith("generate_"))
    repairs = sum(v["repairs"] for k, v in llm.items() if k.startswith("generate_"))
    nq = len(to_solve)
    return SuiteResult(
        "generation",
        {
            "sets": len(jobs),
            "generation_success_rate": round(gen_ok / len(jobs), 3),
            "repair_rate": round(repairs / calls, 3) if calls else 0.0,
            "questions": nq,
            "solver_agreement": round((nq - disagree) / nq, 3) if nq else 0.0,
        },
        failures,
    )


class ExplainVerdict(BaseModel):
    states_correct_answer: bool
    factually_correct: bool
    explains_why_user_wrong: bool
    issues: list[str]


EXPLAIN_JUDGE_SYSTEM = (
    "Bạn là giám khảo chuyên môn tiếng Anh. Chấm lời giải thích của một gia sư AI cho câu TOEIC. "
    "Nghiêm khắc với mọi phát biểu ngữ pháp sai."
)


async def explain(limit: int | None = None) -> SuiteResult:
    items = load_jsonl("part5_golden.jsonl")[:limit]

    async def one(item):
        letters = "ABCD"
        wrong = letters[(letters.index(item["correct_answer"]) + 1) % 4]
        expl = await llm_service.explain_answer(
            question=f"{item['content']}\nĐáp án: {', '.join(item['options'])}",
            user_answer=wrong, correct_answer=item["correct_answer"], part="part5",
        )
        prompt = (
            f"Câu hỏi: {item['content']}\nĐáp án: {item['options']}\n"
            f"Đáp án đúng: {item['correct_answer']} | Học sinh chọn: {wrong}\n\n"
            f"Lời giải thích cần chấm:\n\"\"\"\n{expl}\n\"\"\"\n\n"
            "Trả về JSON: {\"states_correct_answer\": bool, \"factually_correct\": bool, "
            "\"explains_why_user_wrong\": bool, \"issues\": [\"...\"]}"
        )
        v = await ev.ask_json(ev.judge_model(), EXPLAIN_JUDGE_SYSTEM, prompt, ExplainVerdict)
        return item, v

    rows = await asyncio.gather(*(one(i) for i in items))
    failures = []
    passed = 0
    for item, v in rows:
        ok = v.states_correct_answer and v.factually_correct and v.explains_why_user_wrong
        passed += ok
        if not ok:
            failures.append({"id": item["id"], "verdict": v.model_dump()})
    n = len(rows)
    return SuiteResult("explain", {"n": n, "pass_rate": round(passed / n, 3)}, failures)


class ChatVerdict(BaseModel):
    covered: list[bool]
    incorrect_claims: list[str]


CHAT_JUDGE_SYSTEM = (
    "Bạn là giám khảo chuyên môn tiếng Anh. Kiểm tra câu trả lời của chatbot luyện thi "
    "có nêu đúng các ý chính và có phát biểu sai nào không."
)


async def chat(limit: int | None = None) -> SuiteResult:
    items = load_jsonl("chat_golden.jsonl")[:limit]

    async def one(item):
        reply = await llm_service.chat(message=item["question"], history=[])
        kp = "\n".join(f"{i + 1}. {k}" for i, k in enumerate(item["key_points"]))
        prompt = (
            f"Câu hỏi: {item['question']}\n\nCác ý chính bắt buộc:\n{kp}\n\n"
            f"Câu trả lời của chatbot:\n\"\"\"\n{reply}\n\"\"\"\n\n"
            f"Trả về JSON: {{\"covered\": [{len(item['key_points'])} giá trị bool theo thứ tự ý chính], "
            "\"incorrect_claims\": [\"phát biểu sai, nếu có\"]}"
        )
        v = await ev.ask_json(ev.judge_model(), CHAT_JUDGE_SYSTEM, prompt, ChatVerdict)
        return item, v

    rows = await asyncio.gather(*(one(i) for i in items))
    total_kp = covered = with_errors = 0
    failures = []
    for item, v in rows:
        k = len(item["key_points"])
        c = sum(bool(x) for x in v.covered[:k])
        total_kp += k
        covered += c
        with_errors += bool(v.incorrect_claims)
        if c < k or v.incorrect_claims:
            failures.append({
                "id": item["id"],
                "missing": [kp for kp, ok in zip(item["key_points"], v.covered + [False] * k) if not ok],
                "incorrect_claims": v.incorrect_claims,
            })
    n = len(rows)
    return SuiteResult(
        "chat",
        {
            "n": n,
            "key_point_coverage": round(covered / total_kp, 3) if total_kp else 0.0,
            "answers_with_errors_rate": round(with_errors / n, 3),
        },
        failures,
    )


SUITES = {
    "solver_baseline": solver_baseline,
    "generation": generation,
    "explain": explain,
    "chat": chat,
}
