"""Jev (TypeSafe AI) — model "System One": không sinh text, chỉ ra quyết định có xác suất.

ViEng dùng Jev theo mô hình "LLM viết, Jev quyết định, code hành động":
- verify_questions: làm thử câu trắc nghiệm do LLM sinh -> phát hiện đáp án sai/mơ hồ.
- needs_rag: quyết định câu chat có cần tra knowledge base hay không.

Mọi lỗi của Jev đều fail-open (bỏ qua bước kiểm tra), không chặn luồng chính.
API: POST {base}/systemone  body {model, state, questions{name: {type, instructions, criteria}}}
     -> {answers: {name: {choice|score|noul, confidence?, probabilities?}}}
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from loguru import logger

from app.core.config import get_settings
from app.core.observability import llm_span

LETTERS = ("A", "B", "C", "D")


@dataclass
class MCQVerdict:
    index: int          # thứ tự câu (0-based) trong bộ đề
    key: str            # đáp án của đề
    choice: str | None  # Jev chọn
    confidence: float


class JevService:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    @property
    def enabled(self) -> bool:
        return bool(get_settings().typesafe_api_key)

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            s = get_settings()
            self._client = httpx.AsyncClient(
                base_url=s.jev_base_url.rstrip("/"),
                headers={"Authorization": f"Bearer {s.typesafe_api_key}"},
                timeout=s.jev_timeout_s,
            )
        return self._client

    async def ask(self, state: dict, questions: dict, *, task: str) -> dict:
        """Gọi Jev. Trả về dict answers; ném lỗi nếu HTTP/format sai (caller tự fail-open)."""
        s = get_settings()
        async with llm_span(task, s.jev_model):
            r = await self._http().post(
                "/systemone",
                json={"model": s.jev_model, "state": state, "questions": questions},
            )
            r.raise_for_status()
            answers = r.json().get("answers")
            if not isinstance(answers, dict):
                raise ValueError("Jev response thiếu 'answers'.")
            return answers

    # ------------------------------------------------------------------
    # 1) Kiểm tra câu trắc nghiệm do LLM sinh
    # ------------------------------------------------------------------
    async def verify_questions(self, items: list[tuple[str, str, list[str], str]]) -> list[MCQVerdict] | None:
        """items = [(context, question, options["A. ..",..], key)]. None nếu tắt/lỗi."""
        if not self.enabled or not items:
            return None
        questions = {}
        for i, (_ctx, q, options, _key) in enumerate(items):
            criteria = {}
            for letter, opt in zip(LETTERS, options):
                body = opt.split(". ", 1)[1] if opt[:2] == f"{letter}." else opt
                criteria[letter] = {"what": body}
            questions[f"q{i}"] = {
                "type": "choice",
                "instructions": {
                    "question": f"Which option is the single correct answer to question {i + 1}? {q}",
                    "focus": "English grammar, vocabulary and meaning in context of the passage (if any).",
                },
                "criteria": criteria,
            }
        contexts = sorted({c for c, *_ in items if c})
        state = {"exam": "TOEIC Reading", "passages": contexts} if contexts else {"exam": "TOEIC Reading Part 5"}
        try:
            answers = await self.ask(state, questions, task="jev_verify_questions")
        except Exception as e:  # noqa: BLE001 - fail-open
            logger.warning("Jev verify bỏ qua: {}", e)
            return None
        out = []
        for i, (_c, _q, _o, key) in enumerate(items):
            a = answers.get(f"q{i}") or {}
            out.append(MCQVerdict(i, key, a.get("choice"), float(a.get("confidence") or 0.0)))
        return out

    def disagreement_errors(self, verdicts: list[MCQVerdict] | None) -> list[str]:
        """Biến kết quả Jev thành lỗi cho vòng tự sửa của LLM."""
        if not verdicts:
            return []
        thr = get_settings().jev_verify_threshold
        errs = []
        for v in verdicts:
            if v.choice and v.choice != v.key and v.confidence >= thr:
                errs.append(
                    f"Câu {v.index + 1}: kiểm tra độc lập chọn {v.choice} (độ tin cậy {v.confidence:.2f}) "
                    f"nhưng đáp án đề là {v.key}. Sửa đáp án hoặc viết lại câu để chỉ có một đáp án đúng."
                )
        return errs

    # ------------------------------------------------------------------
    # 2) Chat: có cần tra RAG không?
    # ------------------------------------------------------------------
    async def needs_rag(self, message: str) -> bool:
        """True nếu nên tra knowledge base. Tắt/lỗi -> True (giữ hành vi cũ)."""
        if not self.enabled or not get_settings().jev_rag_gate:
            return True
        questions = {
            "needs_reference": {
                "type": "noul",
                "instructions": (
                    "Does answering this learner message benefit from looking up English grammar, "
                    "vocabulary or TOEIC/IELTS reference material?"
                ),
                "criteria": {
                    "true": {"what": "a question about grammar, vocabulary, usage, exam format or tips",
                             "examples": ["Khi nào dùng thì hiện tại hoàn thành?", "since và for khác nhau?"]},
                    "false": {"what": "greeting, thanks, small talk or a request unrelated to English",
                              "examples": ["xin chào", "cảm ơn bạn", "bạn là ai?"]},
                },
            }
        }
        try:
            answers = await self.ask({"message": message[:2000]}, questions, task="jev_rag_gate")
            p = float((answers.get("needs_reference") or {}).get("noul", 1.0))
        except Exception as e:  # noqa: BLE001 - fail-open
            logger.warning("Jev RAG gate bỏ qua: {}", e)
            return True
        return p >= get_settings().jev_rag_threshold


jev_service = JevService()
