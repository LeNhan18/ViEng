"""Structured LLM outputs: schema dành riêng cho LLM + validator nghiệp vụ.

Schema ở đây cố tình KHÔNG có giá trị mặc định / field tuỳ chọn để tương thích
OpenAI Structured Outputs (strict JSON Schema). Id câu hỏi do server gán, không
tin vào id model trả về.
"""

from __future__ import annotations

import json
import re
from typing import Callable, Literal

from pydantic import BaseModel, ValidationError

from app.models.schemas import Part6Passage, Part7Passage, Question

LETTERS = ("A", "B", "C", "D")


# ---------------------------------------------------------------------------
# Schema output của LLM
# ---------------------------------------------------------------------------
class LLMQuestion(BaseModel):
    content: str
    options: list[str]
    correct_answer: Literal["A", "B", "C", "D"]


class QuestionSet(BaseModel):
    questions: list[LLMQuestion]


class LLMPart6Passage(BaseModel):
    passage: str
    questions: list[LLMQuestion]


class Part6Set(BaseModel):
    passages: list[LLMPart6Passage]


class LLMPart7Passage(BaseModel):
    passages: list[str]
    questions: list[LLMQuestion]


class Part7Set(BaseModel):
    passages: list[LLMPart7Passage]


class LLMVocabulary(BaseModel):
    word: str
    meaning: str
    example: str


class TranslationResult(BaseModel):
    translated: str
    vocabulary: list[LLMVocabulary]
    grammar_notes: list[str]


class StructuredOutputError(RuntimeError):
    """LLM không trả về output hợp lệ sau khi đã cho tự sửa."""

    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.errors = errors or []


# ---------------------------------------------------------------------------
# Parse JSON thô (dùng khi provider không hỗ trợ structured outputs)
# ---------------------------------------------------------------------------
_FENCE = re.compile(r"^```[a-zA-Z]*\n|\n?```\s*$")


def extract_json(raw: str):
    text = (raw or "").strip()
    text = _FENCE.sub("", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Lấy khối JSON đầu tiên trong chuỗi (model hay thêm lời dẫn).
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        raise ValueError("Không tìm thấy JSON trong output.")
    start = min(starts)
    end = max(text.rfind("}"), text.rfind("]"))
    return json.loads(text[start : end + 1])


def coerce_to_schema(data, schema: type[BaseModel]) -> BaseModel:
    """Chấp nhận cả dạng cũ (JSON array trần) bằng cách bọc vào field list duy nhất."""
    if isinstance(data, list):
        field = next(iter(schema.model_fields))
        data = {field: data}
    return schema.model_validate(data)


# ---------------------------------------------------------------------------
# Chuẩn hoá + validate nghiệp vụ
# ---------------------------------------------------------------------------
_PREFIX = re.compile(r"^\s*\(?([A-Da-d])[\.\):]\s*")


def normalize_options(options: list[str]) -> list[str]:
    out = []
    for i, opt in enumerate(options[:4]):
        body = _PREFIX.sub("", opt).strip()
        out.append(f"{LETTERS[i]}. {body}")
    return out


def _question_errors(q: LLMQuestion, label: str) -> list[str]:
    errs = []
    if not q.content.strip():
        errs.append(f"{label}: content rỗng.")
    if len(q.options) != 4:
        errs.append(f"{label}: cần đúng 4 đáp án, đang có {len(q.options)}.")
    bodies = [_PREFIX.sub("", o).strip().lower() for o in q.options]
    if any(not b for b in bodies):
        errs.append(f"{label}: có đáp án rỗng.")
    if len(set(bodies)) != len(bodies):
        errs.append(f"{label}: các đáp án bị trùng nhau.")
    return errs


def _expect_count(errs: list[str], actual: int, expected: int, what: str) -> None:
    if actual < expected:
        errs.append(f"Cần {expected} {what}, đang có {actual}.")


def validate_question_set(obj: QuestionSet, expected: int, *, require_blank: bool) -> list[str]:
    errs: list[str] = []
    _expect_count(errs, len(obj.questions), expected, "câu hỏi")
    for i, q in enumerate(obj.questions[:expected], 1):
        errs += _question_errors(q, f"Câu {i}")
        if require_blank and "_" not in q.content:
            errs.append(f"Câu {i}: câu Part 5 phải có chỗ trống '___'.")
    return errs


def validate_part6(obj: Part6Set, expected_passages: int) -> list[str]:
    errs: list[str] = []
    _expect_count(errs, len(obj.passages), expected_passages, "đoạn văn")
    for p_i, p in enumerate(obj.passages[:expected_passages], 1):
        if len(p.passage.split()) < 40:
            errs.append(f"Đoạn {p_i}: đoạn văn quá ngắn.")
        if len(p.questions) != 4:
            errs.append(f"Đoạn {p_i}: cần đúng 4 câu hỏi, đang có {len(p.questions)}.")
        for q_i, q in enumerate(p.questions, 1):
            errs += _question_errors(q, f"Đoạn {p_i} câu {q_i}")
    return errs


def validate_part7(obj: Part7Set, expected_passages: int, *, multiple: bool) -> list[str]:
    errs: list[str] = []
    _expect_count(errs, len(obj.passages), expected_passages, "bài đọc")
    for p_i, p in enumerate(obj.passages[:expected_passages], 1):
        n_texts = len([t for t in p.passages if t.strip()])
        if multiple and not 2 <= n_texts <= 3:
            errs.append(f"Bộ {p_i}: cần 2-3 đoạn văn liên quan, đang có {n_texts}.")
        if not multiple and n_texts != 1:
            errs.append(f"Bài {p_i}: cần đúng 1 đoạn văn, đang có {n_texts}.")
        lo, hi = (5, 5) if multiple else (2, 4)
        if not lo <= len(p.questions) <= hi:
            errs.append(f"Bài {p_i}: cần {lo}-{hi} câu hỏi, đang có {len(p.questions)}.")
        for q_i, q in enumerate(p.questions, 1):
            errs += _question_errors(q, f"Bài {p_i} câu {q_i}")
    return errs


def validate_translation(obj: TranslationResult) -> list[str]:
    return [] if obj.translated.strip() else ["translated rỗng."]


Validator = Callable[[BaseModel], list[str]]


# ---------------------------------------------------------------------------
# Chuyển sang schema API (gán id liên tục, chuẩn hoá đáp án)
# ---------------------------------------------------------------------------
def _to_question(q: LLMQuestion, qid: int) -> Question:
    return Question(
        id=qid,
        content=q.content.strip(),
        options=normalize_options(q.options),
        correct_answer=q.correct_answer,
    )


def to_questions(obj: QuestionSet, limit: int) -> list[Question]:
    return [_to_question(q, i) for i, q in enumerate(obj.questions[:limit], 1)]


def to_part6(obj: Part6Set, limit: int) -> list[Part6Passage]:
    qid, out = 1, []
    for p in obj.passages[:limit]:
        qs = []
        for q in p.questions:
            qs.append(_to_question(q, qid))
            qid += 1
        out.append(Part6Passage(passage=p.passage, questions=qs))
    return out


def to_part7(obj: Part7Set, limit: int) -> list[Part7Passage]:
    qid, out = 1, []
    for p in obj.passages[:limit]:
        qs = []
        for q in p.questions:
            qs.append(_to_question(q, qid))
            qid += 1
        out.append(Part7Passage(passages=p.passages, questions=qs))
    return out


def format_validation_error(e: ValidationError) -> list[str]:
    return [f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()[:10]]
