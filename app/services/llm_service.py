import json

from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.models.schemas import Skill, Level, ExamType, ToeicReadingPart
from app.services.rag_service import rag_service
from app.core.observability import llm_span, make_async_openai_client
from app.services.jev_service import jev_service
from app.services.structured import (
    Part6Set,
    Part7Set,
    QuestionSet,
    StructuredOutputError,
    TranslationResult,
    coerce_to_schema,
    extract_json,
    format_validation_error,
    to_part6,
    to_part7,
    to_questions,
    validate_part6,
    validate_part7,
    validate_question_set,
    validate_translation,
)
from loguru import logger
import random

class LLMNotConfiguredError(RuntimeError):
    """Chưa có API key/model cho LLM."""


SYSTEM_PROMPT = (
    "Bạn là giáo viên luyện thi TOEIC/IELTS chuyên nghiệp tại Việt Nam. "
    "Khi được cung cấp tài liệu tham khảo, hãy sử dụng nội dung đó để tạo câu hỏi/giải thích chính xác hơn. "
    "Luôn trả về JSON hợp lệ khi được yêu cầu."
)

GRAMMAR_TOPICS = [
    "verb tenses (present, past, future perfect/continuous)",
    "word forms (nouns, verbs, adjectives, adverbs)",
    "subject-verb agreement",
    "passive voice",
    "conditionals & inversions (type 1, 2, 3, mixed)",
    "conjunctions & connectors (although, because, however, etc.)",
    "relative clauses & reduced relative clauses",
    "comparisons (comparatives, superlatives, double comparisons)",
    "gerunds vs infinitives (to-infinitive, bare infinitive, -ing)",
    "reported speech & subjunctive mood",
    "articles and quantifiers (some, any, much, many, each, every)",
    "prepositions of time, place, and direction",
    "phrasal verbs & collocations",
]

BUSINESS_TOPICS = [
    "office administration & workplace management (supplies, memos, meetings)",
    "recruitment, hiring, human resources & employee benefits",
    "marketing, sales, advertising campaigns & customer feedback",
    "shipping, logistics, inventory management & deliveries",
    "business travel, conferences, trade shows & corporate events",
    "financial services, banking, accounting, budgeting & invoices",
    "contracts, negotiations, business agreements & partnership proposals",
    "customer support, client relations & product warranties",
    "purchasing, ordering, store transactions & retail management",
    "technology, software updates, online security & IT troubleshooting",
]


class LLMService:
    """Quản lý tương tác với LLM (OpenAI/Groq hoặc fine-tuned model trên HF)."""

    def __init__(self):
        settings = get_settings()
        self._openai_client = None
        self._client = None          # client OpenAI-compatible đang dùng
        self._vendor = ""            # "anthropic" | "openrouter" | ""
        self._model_name = ""
        self._hf_model = None
        self._hf_tokenizer = None

        if settings.use_finetuned_model and settings.hf_model_name:
            logger.info(
                f"Sẽ dùng fine-tuned model: {settings.hf_model_name} (provider={settings.llm_provider})"
            )
        # Tắt structured outputs nếu provider/model không hỗ trợ (tự phát hiện).
        self._structured_supported = True

        provider = (settings.llm_provider or "auto").strip().lower()
        use_anthropic = bool(settings.anthropic_api_key) and provider in ("auto", "anthropic")
        if provider == "anthropic" and not settings.anthropic_api_key:
            logger.warning("LLM_PROVIDER=anthropic nhưng thiếu ANTHROPIC_API_KEY.")

        if use_anthropic:
            self._client = make_async_openai_client(
                base_url=settings.anthropic_base_url,
                api_key=settings.anthropic_api_key,
                timeout=60.0,
                max_retries=2,
            )
            self._vendor = "anthropic"
            self._model_name = settings.anthropic_model
            # Endpoint OpenAI-compat của Anthropic bỏ qua response_format -> dùng JSON text mode.
            self._structured_supported = False
            logger.info("LLM: Claude API, model={}", self._model_name)
        elif settings.openrouter_api_key:
            self._client = make_async_openai_client(
                base_url="https://openrouter.ai/api/v1",
                api_key=settings.openrouter_api_key,
                timeout=60.0,
                max_retries=2,
            )
            self._vendor = "openrouter"
            logger.info("LLM: OpenRouter, model={}", settings.llm_model)

    # Tên cũ, giữ để tương thích (test/eval cũ dùng thuộc tính này).
    @property
    def _openrouter_client(self):
        return self._client

    @_openrouter_client.setter
    def _openrouter_client(self, value):
        self._client = value

    @property
    def model(self) -> str:
        return self._model_name or get_settings().llm_model

    def _sampling(self, temperature: float | None) -> dict:
        """Claude đời mới trả 400 nếu temperature < 1 -> không gửi temperature cho Anthropic."""
        if self._vendor == "anthropic" or temperature is None:
            return {}
        return {"temperature": temperature}

    def _provider(self, override: str | None = None) -> str:
        settings = get_settings()
        p = (override or settings.llm_provider or "auto").strip().lower()
        if p not in ("auto", "anthropic", "openrouter", "hf_inference", "hf_local"):
            logger.warning(f"LLM provider không hợp lệ: {override or settings.llm_provider} -> dùng auto")
            return "auto"
        return p

    def _load_hf_model(self):
        """Lazy-load fine-tuned model từ HuggingFace (chỉ gọi khi cần)."""
        if self._hf_model is not None:
            return

        settings = get_settings()
        logger.info(f"Loading fine-tuned model: {settings.hf_model_name}")

        try:
            import torch
            from transformers import AutoTokenizer, AutoModelForCausalLM
            self._hf_tokenizer = AutoTokenizer.from_pretrained(settings.hf_model_name)
            self._hf_model = AutoModelForCausalLM.from_pretrained(
                settings.hf_model_name,
                torch_dtype=torch.float16,
                device_map="auto",
                load_in_4bit=True,
            )
            logger.info("Fine-tuned model loaded successfully!")
        except Exception as e:
            logger.error(f"Không thể load fine-tuned model: {e}")
            logger.info("Fallback sang Groq/OpenAI API")
            self._hf_model = None

    async def _generate_with_hf(self, prompt: str, max_tokens: int = 1000, system_msg: str = "", temperature: float = 0.7) -> str:
        """Generate text bằng fine-tuned model local."""
        import torch

        self._load_hf_model()
        if self._hf_model is None:
            raise RuntimeError("Fine-tuned model chưa sẵn sàng")

        messages = []
        if system_msg:
            messages.append({"role": "system", "content": system_msg})
        messages.append({"role": "user", "content": prompt})

        inputs = self._hf_tokenizer.apply_chat_template(
            messages, tokenize=True, add_generation_prompt=True, return_tensors="pt"
        ).to(self._hf_model.device)

        with torch.no_grad():
            outputs = self._hf_model.generate(
                input_ids=inputs,
                max_new_tokens=max_tokens,
                temperature=temperature,
                do_sample=True,
            )

        return self._hf_tokenizer.decode(outputs[0][inputs.shape[-1]:], skip_special_tokens=True)

    async def _generate_with_hf_inference(
        self, prompt: str, max_tokens: int = 1000, system_msg: str = "", temperature: float = 0.7
    ) -> str:
        """
        Generate text bằng Hugging Face Inference API (không load model local).
        Phù hợp khi model đã public trên HF: https://huggingface.co/LeNhan18/ViEng-Qwen2.5-7B-lora
        """
        settings = get_settings()
        if not settings.hf_model_name:
            raise RuntimeError("Thiếu HF_MODEL_NAME")

        try:
            from huggingface_hub import InferenceClient
        except Exception as e:
            raise RuntimeError(
                "Chưa cài huggingface-hub. Hãy pip install -r requirements.txt"
            ) from e

        client = getattr(self, "_hf_inference_client", None)
        if client is None:
            client = InferenceClient(model=settings.hf_model_name, token=(settings.hf_token or None))
            self._hf_inference_client = client  # tạo 1 lần, tái sử dụng kết nối

        # Gộp system + user thành 1 prompt thuần để gọi text-generation.
        # (Giữ tương thích với pipeline prompt hiện tại.)
        full_prompt = prompt
        if system_msg:
            full_prompt = f"{system_msg}\n\n{prompt}"

        # Inference API là sync, chạy trong thread để không block event loop.
        import asyncio

        def _run():
            return client.text_generation(
                full_prompt,
                max_new_tokens=max_tokens,
                temperature=temperature,
                do_sample=True,
                return_full_text=False,
            )

        return await asyncio.to_thread(_run)

    @property
    def _client_and_model(self) -> tuple:
        if self._client:
            return self._client, self.model
        raise LLMNotConfiguredError(
            "Chưa cấu hình API key. Thêm ANTHROPIC_API_KEY hoặc OPENROUTER_API_KEY vào .env"
        )

    @property
    def _use_finetuned(self) -> bool:
        settings = get_settings()
        return settings.use_finetuned_model and settings.hf_model_name

    async def _call_finetuned(
        self, prompt: str, max_tokens: int, system_msg: str, *, provider_override: str | None = None, temperature: float = 0.7
    ) -> str:
        p = self._provider(provider_override)
        if p in ("hf_inference",):
            return await self._generate_with_hf_inference(prompt, max_tokens=max_tokens, system_msg=system_msg, temperature=temperature)
        # "auto" hoặc "hf_local" -> ưu tiên local (giữ kỹ thuật cũ)
        return await self._generate_with_hf(prompt, max_tokens=max_tokens, system_msg=system_msg, temperature=temperature)

    def _build_rag_context_section(self, rag_context: str) -> str:
        """Tạo đoạn RAG context để chèn vào prompt."""
        if not rag_context:
            return ""
        return (
            "\n\nTài liệu tham khảo ngữ pháp/từ vựng (dùng để tạo câu hỏi chính xác hơn):\n"
            f"---\n{rag_context}\n---\n"
        )

    def _retrieve_for_part(self, part: str, level: Level, extra_query: str = "") -> str:
        """Retrieve RAG context phù hợp cho từng dạng Part."""
        queries = {
            "part5": f"TOEIC Part 5 grammar rules word forms tenses prepositions {level.value}",
            "part6": f"TOEIC Part 6 connectors conjunctions text completion grammar {level.value}",
            "part7_single": f"TOEIC Part 7 reading comprehension vocabulary business {level.value}",
            "part7_multiple": f"TOEIC Part 7 multiple passages vocabulary business communication {level.value}",
        }
        base_query = queries.get(part, f"TOEIC grammar vocabulary {level.value}")
        if extra_query:
            query = f"{base_query} {extra_query}"
        else:
            query = base_query
        return rag_service.retrieve_mmr(query, k=3)

    def _build_part5_prompt(
        self, level: Level, num_questions: int, rag_context: str = "", grammar_topic: str = "", business_topic: str = ""
    ) -> str:
        base = f"Tạo {num_questions} câu hỏi TOEIC Reading Part 5 (Incomplete Sentences) trình độ {level.value}.\n\n"
        if grammar_topic:
            base += f"- Trọng tâm ngữ pháp cần kiểm tra: {grammar_topic}\n"
        if business_topic:
            base += f"- Ngữ cảnh/Chủ đề từ vựng: {business_topic}\n"

        base += (
            "\nFormat chuẩn TOEIC Part 5:\n"
            "- Mỗi câu là 1 câu tiếng Anh có 1 chỗ trống (___)\n"
            "- 4 đáp án A, B, C, D\n"
            "- Kiểm tra ngữ pháp (thì, dạng từ, giới từ, mệnh đề quan hệ...) hoặc từ vựng\n"
        )   
        base += self._build_rag_context_section(rag_context)
        base += (
            "\nTrả về JSON array:\n"
            '[{"id": 1, "content": "The manager ___ the report before the meeting.", '
            '"options": ["A. review", "B. reviewed", "C. reviewing", "D. reviews"], '
            '"correct_answer": "B"}]\n'
            "Chỉ trả về JSON, không thêm text."
        )
        return base

    def _build_part6_prompt(
        self, level: Level, num_passages: int, rag_context: str = "", grammar_topic: str = "", business_topic: str = ""
    ) -> str:
        base = f"Tạo {num_passages} đoạn văn TOEIC Reading Part 6 (Text Completion) trình độ {level.value}.\n\n"
        if grammar_topic:
            base += f"- Trọng tâm ngữ pháp cần kiểm tra: {grammar_topic}\n"
        if business_topic:
            base += f"- Ngữ cảnh/Chủ đề từ vựng: {business_topic}\n"

        base += (
            "\nFormat chuẩn TOEIC Part 6:\n"
            "- Mỗi đoạn là 1 email/memo/thông báo/bài báo ngắn (100-150 từ)\n"
            "- Mỗi đoạn có đúng 4 chỗ trống đánh số (1), (2), (3), (4)\n"
            "- Mỗi chỗ trống có 4 đáp án A, B, C, D\n"
            "- Có thể hỏi: điền từ, điền cụm từ, hoặc điền cả câu phù hợp ngữ cảnh\n"
        )
        base += self._build_rag_context_section(rag_context)
        base += (
            "\nTrả về JSON array, mỗi phần tử là 1 đoạn:\n"
            '[{"passage": "Dear Mr. Smith,\\nWe are pleased to inform you that your application has been (1)___. '
            'Please (2)___ the attached document...\\n...", '
            '"questions": [{"id": 1, "content": "(1)", "options": ["A. accepted", "B. accepting", "C. accept", "D. acceptable"], "correct_answer": "A"}, '
            '{"id": 2, "content": "(2)", "options": [...], "correct_answer": "..."}, '
            '{"id": 3, ...}, {"id": 4, ...}]}]\n'
            "Chỉ trả về JSON, không thêm text."
        )
        return base

    def _build_part7_single_prompt(
        self, level: Level, num_passages: int, rag_context: str = "", grammar_topic: str = "", business_topic: str = ""
    ) -> str:
        base = f"Tạo {num_passages} bài đọc TOEIC Reading Part 7 Single Passage trình độ {level.value}.\n\n"
        if grammar_topic:
            base += f"- Trọng tâm ngữ pháp cần lồng ghép: {grammar_topic}\n"
        if business_topic:
            base += f"- Ngữ cảnh/Chủ đề từ vựng chính: {business_topic}\n"

        base += (
            "\nFormat chuẩn TOEIC Part 7 Single:\n"
            "- Mỗi bài là 1 đoạn văn (email, quảng cáo, thông báo, tin nhắn, bài báo) dài 150-250 từ\n"
            "- Mỗi bài có 2-4 câu hỏi\n"
            "- Dạng câu hỏi: ý chính, chi tiết, suy luận, từ đồng nghĩa, mục đích người viết\n"
        )
        base += self._build_rag_context_section(rag_context)
        base += (
            "\nTrả về JSON array:\n"
            '[{"passages": ["Dear Employees,\\nWe are excited to announce..."], '
            '"questions": [{"id": 1, "content": "What is the purpose of the email?", '
            '"options": ["A. To announce a policy change", "B. To request information", '
            '"C. To confirm a meeting", "D. To introduce a new employee"], '
            '"correct_answer": "A"}, ...]}]\n'
            "Chỉ trả về JSON, không thêm text."
        )
        return base

    def _build_part7_multiple_prompt(
        self, level: Level, num_sets: int, rag_context: str = "", grammar_topic: str = "", business_topic: str = ""
    ) -> str:
        base = f"Tạo {num_sets} bộ TOEIC Reading Part 7 Multiple Passages trình độ {level.value}.\n\n"
        if grammar_topic:
            base += f"- Trọng tâm ngữ pháp cần lồng ghép: {grammar_topic}\n"
        if business_topic:
            base += f"- Ngữ cảnh/Chủ đề từ vựng chính: {business_topic}\n"

        base += (
            "\nFormat chuẩn TOEIC Part 7 Multiple:\n"
            "- Mỗi bộ gồm 2-3 đoạn văn liên quan (email + reply, quảng cáo + review, memo + schedule...)\n"
            "- Mỗi bộ có 5 câu hỏi\n"
            "- Câu hỏi yêu cầu liên kết thông tin giữa các đoạn\n"
        )
        base += self._build_rag_context_section(rag_context)
        base += (
            "\nTrả về JSON array:\n"
            '[{"passages": ["From: john@company.com\\nSubject: Team Building Event\\n...", '
            '"From: sarah@company.com\\nSubject: Re: Team Building Event\\n..."], '
            '"questions": [{"id": 1, "content": "What does John suggest?", '
            '"options": ["A. ...", "B. ...", "C. ...", "D. ..."], '
            '"correct_answer": "A"}, ... (5 câu hỏi)]}]\n'
            "Chỉ trả về JSON, không thêm text."
        )
        return base

    async def _call_llm(
        self,
        prompt: str,
        max_tokens: int = 2000,
        system_msg: str = "",
        *,
        provider_override: str | None = None,
        temperature: float | None = None,
        task: str = "generic",
    ) -> str:
        sys_content = system_msg or SYSTEM_PROMPT
        temp = temperature if temperature is not None else round(random.uniform(0.75, 0.9), 2)

        if self._use_finetuned:
            async with llm_span(task, get_settings().hf_model_name):
                return await self._call_finetuned(
                    prompt, max_tokens=max_tokens, system_msg=sys_content,
                    provider_override=provider_override, temperature=temp,
                )

        client, model = self._client_and_model
        async with llm_span(task, model) as span:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": sys_content},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_tokens,
                **self._sampling(temp),
            )
            span.add_usage(getattr(response, "usage", None))
            return response.choices[0].message.content

    # ------------------------------------------------------------------
    # Structured outputs + validate + self-repair
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_method(client):
        """openai>=1.92 có chat.completions.parse; bản cũ nằm ở beta."""
        comp = getattr(getattr(client, "chat", None), "completions", None)
        if comp is not None and hasattr(comp, "parse"):
            return comp.parse
        beta = getattr(client, "beta", None)
        if beta is not None:
            return beta.chat.completions.parse
        return None

    async def _structured_attempt(
        self, messages: list[dict], schema: type[BaseModel], *, max_tokens: int,
        temperature: float, provider_override: str | None, span,
    ) -> tuple[BaseModel | None, str, list[str]]:
        """1 lần gọi. Trả về (object|None, raw_text, schema_errors)."""
        if self._use_finetuned:
            prompt = "\n\n".join(m["content"] for m in messages[1:])
            raw = await self._call_finetuned(
                prompt, max_tokens=max_tokens, system_msg=messages[0]["content"],
                provider_override=provider_override, temperature=temperature,
            )
            return self._parse_raw(raw, schema)

        client, model = self._client_and_model
        parse = self._parse_method(client) if self._structured_supported else None
        if parse is not None:
            try:
                resp = await parse(
                    model=model, messages=messages, response_format=schema,
                    max_tokens=max_tokens, **self._sampling(temperature),
                )
                span.add_usage(getattr(resp, "usage", None))
                msg = resp.choices[0].message
                raw = msg.content or ""
                if getattr(msg, "parsed", None) is not None:
                    return msg.parsed, raw, []
                if getattr(msg, "refusal", None):
                    return None, raw, [f"Model từ chối: {msg.refusal}"]
                return self._parse_raw(raw, schema)
            except ValidationError as e:
                return None, "", format_validation_error(e)
            except Exception as e:  # noqa: BLE001
                # Provider/model không hỗ trợ json_schema -> chuyển hẳn sang text mode.
                if e.__class__.__name__ in ("BadRequestError", "UnprocessableEntityError", "NotFoundError"):
                    logger.warning("Structured outputs không được hỗ trợ ({}); dùng JSON text mode.", e)
                    self._structured_supported = False
                else:
                    raise

        resp = await client.chat.completions.create(
            model=model, messages=messages, max_tokens=max_tokens, **self._sampling(temperature),
        )
        span.add_usage(getattr(resp, "usage", None))
        return self._parse_raw(resp.choices[0].message.content or "", schema)

    @staticmethod
    def _parse_raw(raw: str, schema: type[BaseModel]) -> tuple[BaseModel | None, str, list[str]]:
        try:
            return coerce_to_schema(extract_json(raw), schema), raw, []
        except ValidationError as e:
            return None, raw, format_validation_error(e)
        except (ValueError, json.JSONDecodeError) as e:
            return None, raw, [f"JSON không hợp lệ: {e}"]

    async def _generate_structured(
        self,
        prompt: str,
        schema: type[BaseModel],
        validator,
        *,
        task: str,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        system_msg: str = "",
        provider_override: str | None = None,
        verifier=None,
    ) -> BaseModel:
        """Gọi LLM -> parse theo schema -> validate nghiệp vụ -> cho LLM tự sửa nếu lỗi."""
        settings = get_settings()
        messages = [
            {"role": "system", "content": system_msg or SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        model = settings.hf_model_name if self._use_finetuned else self.model
        errors: list[str] = []
        async with llm_span(task, model) as span:
            for attempt in range(settings.llm_max_repairs + 1):
                obj, raw, errors = await self._structured_attempt(
                    messages, schema, max_tokens=max_tokens, temperature=temperature,
                    provider_override=provider_override, span=span,
                )
                if obj is not None and not errors:
                    errors = validator(obj)
                # Kiểm tra độc lập (Jev) chỉ khi đã qua schema + validator: rẻ hơn và tránh nhiễu.
                if obj is not None and not errors and verifier is not None:
                    errors = await verifier(obj)
                if not errors:
                    return obj
                logger.warning("[{}] output lỗi (lần {}): {}", task, attempt + 1, errors[:5])
                if attempt == settings.llm_max_repairs:
                    break
                span.repairs += 1
                previous = raw or (obj.model_dump_json() if obj is not None else "")
                if previous:
                    messages.append({"role": "assistant", "content": previous[:12000]})
                messages.append({
                    "role": "user",
                    "content": (
                        "Output vừa rồi chưa đạt yêu cầu:\n- " + "\n- ".join(errors[:10])
                        + "\nHãy sửa các lỗi trên và trả lại TOÀN BỘ kết quả theo đúng JSON schema. "
                        "Chỉ trả về JSON."
                    ),
                })
                # Giảm nhiệt độ khi sửa để model bám yêu cầu hơn.
                temperature = min(temperature, 0.4)
            raise StructuredOutputError(f"[{task}] LLM không trả về output hợp lệ.", errors)

    @staticmethod
    def _jev_verifier(limit: int):
        """Async verifier: Jev làm thử các câu (trong phạm vi `limit` item đầu) -> lỗi nếu bất đồng."""
        if not (jev_service.enabled and get_settings().jev_verify_questions):
            return None

        async def verify(obj) -> list[str]:
            items = []
            if isinstance(obj, QuestionSet):
                items = [("", q.content, q.options, q.correct_answer) for q in obj.questions[:limit]]
            elif isinstance(obj, Part6Set):
                for p in obj.passages[:limit]:
                    items += [(p.passage, q.content, q.options, q.correct_answer) for q in p.questions]
            elif isinstance(obj, Part7Set):
                for p in obj.passages[:limit]:
                    ctx = "\n\n---\n\n".join(p.passages)
                    items += [(ctx, q.content, q.options, q.correct_answer) for q in p.questions]
            return jev_service.disagreement_errors(await jev_service.verify_questions(items))

        return verify

    async def generate_questions(
        self,
        exam_type: ExamType,
        skill: Skill,
        level: Level,
        num_questions: int,
        part: ToeicReadingPart | None = None,
        *,
        llm_provider: str | None = None,
    ) -> list[dict]:
        """Sinh đề đã được validate. Trả về list dict theo shape API cũ (có id liên tục)."""
        import asyncio

        logger.info(f"Generating questions: {exam_type}/{skill}/{level} part={part} n={num_questions}")

        selected_grammar = random.choice(GRAMMAR_TOPICS)
        selected_business = random.choice(BUSINESS_TOPICS)
        logger.info(f"Topics: grammar={selected_grammar!r} business={selected_business!r}")

        random_temp = round(random.uniform(0.75, 0.9), 2)
        common = dict(temperature=random_temp, provider_override=llm_provider)

        if exam_type == ExamType.TOEIC and skill == Skill.READING and part:
            extra_query = f"{selected_grammar} {selected_business}"
            rag_context = await asyncio.to_thread(self._retrieve_for_part, part.value, level, extra_query)
            if rag_context:
                logger.info(f"RAG context retrieved for {part.value} ({len(rag_context)} chars)")

            if part == ToeicReadingPart.PART5:
                prompt = self._build_part5_prompt(level, num_questions, rag_context, selected_grammar, selected_business)
                obj = await self._generate_structured(
                    prompt, QuestionSet,
                    lambda o: validate_question_set(o, num_questions, require_blank=True),
                    task="generate_part5", max_tokens=2000, verifier=self._jev_verifier(num_questions), **common,
                )
                return [q.model_dump() for q in to_questions(obj, num_questions)]

            if part == ToeicReadingPart.PART6:
                num_passages = max(1, num_questions // 4)
                prompt = self._build_part6_prompt(level, num_passages, rag_context, selected_grammar, selected_business)
                obj = await self._generate_structured(
                    prompt, Part6Set, lambda o: validate_part6(o, num_passages),
                    task="generate_part6", max_tokens=3000, verifier=self._jev_verifier(num_passages), **common,
                )
                return [p.model_dump() for p in to_part6(obj, num_passages)]

            if part in (ToeicReadingPart.PART7_SINGLE, ToeicReadingPart.PART7_MULTIPLE):
                multiple = part == ToeicReadingPart.PART7_MULTIPLE
                n = max(1, num_questions // (5 if multiple else 3))
                build = self._build_part7_multiple_prompt if multiple else self._build_part7_single_prompt
                prompt = build(level, n, rag_context, selected_grammar, selected_business)
                obj = await self._generate_structured(
                    prompt, Part7Set, lambda o: validate_part7(o, n, multiple=multiple),
                    task=f"generate_{part.value}", max_tokens=4000, verifier=self._jev_verifier(n), **common,
                )
                return [p.model_dump() for p in to_part7(obj, n)]

        rag_context = await asyncio.to_thread(
            rag_service.retrieve_mmr,
            f"{exam_type.value} grammar vocabulary {skill.value} {level.value} {selected_grammar} {selected_business}",
            2,
        )
        rag_section = self._build_rag_context_section(rag_context)

        prompt = (
            f"Bạn là một giáo viên luyện thi {exam_type.value.upper()} giàu kinh nghiệm tại Việt Nam.\n"
            f"Hãy tạo {num_questions} câu hỏi {skill.value} trình độ {level.value}.\n"
            f"Chủ đề ngữ pháp cần tập trung: {selected_grammar}.\n"
            f"Bối cảnh câu hỏi: {selected_business}.\n\n"
            f"Yêu cầu:\n"
            f"- Mỗi câu hỏi có đúng 4 đáp án A, B, C, D\n"
            f"- Đánh dấu đáp án đúng\n"
            f"- Nội dung sát format thi {exam_type.value.upper()} thật\n"
            f"{rag_section}\n"
            f"- Trả về JSON với format:\n"
            f'  {{"questions": [{{"content": "...", "options": ["A. ...", "B. ...", "C. ...", "D. ..."], "correct_answer": "A"}}]}}\n'
            f"- Chỉ trả về JSON, không thêm text khác."
        )
        obj = await self._generate_structured(
            prompt, QuestionSet,
            lambda o: validate_question_set(o, num_questions, require_blank=False),
            task=f"generate_{exam_type.value}_{skill.value}", verifier=self._jev_verifier(num_questions), **common,
        )
        return [q.model_dump() for q in to_questions(obj, num_questions)]

    def _part_explanation_guidance(self, part: str | None) -> str:
        """Hướng dẫn giải thích khác nhau theo Part 5/6/7."""
        if not part:
            return ""
        p = (part or "").lower()
        if p == "part5":
            return (
                "Part 5: 1 câu có chỗ trống.\n"
                "Giải thích tập trung vào: ngữ pháp (thì, dạng từ, giới từ, mệnh đề quan hệ...) hoặc từ vựng trong câu đó."
            )
        if p == "part6":
            return (
                "Part 6: đoạn văn có chỗ trống.\n"
                "BẮT BUỘC giải thích dựa trên đoạn văn: phải trích dẫn ngữ cảnh trong đoạn, nối liền với câu trước/sau, "
                "tâm lý người viết, mạch văn. Không chỉ giải thích câu đơn lẻ."
            )
        if p in ("part7_single", "part7_multiple"):
            return (
                "Part 7: bài đọc + câu hỏi đọc hiểu.\n"
                "BẮT BUỘC giải thích dựa trên đoạn văn: trích dẫn câu/đoạn trong bài đọc chứng minh đáp án, "
                "phân tích ngữ cảnh, ý chính, chi tiết, suy luận. Không chỉ dựa vào câu hỏi."
            )
        return ""

    async def explain_answer(
        self,
        question: str,
        user_answer: str,
        correct_answer: str,
        context: str = "",
        *,
        part: str | None = None,
        passage: str = "",
        llm_provider: str | None = None,
    ) -> str:
        prompt = (
            f"Bạn là thầy giáo tiếng Anh Việt Nam, giải thích thân thiện, gần gũi.\n\n"
            f"Câu hỏi: {question}\n"
            f"Đáp án của học sinh: {user_answer}\n"
            f"Đáp án đúng: {correct_answer}\n"
        )
        if passage:
            prompt += f"\n--- ĐOẠN VĂN (ngữ cảnh bắt buộc dùng khi giải thích):\n{passage}\n---\n"
        if context:
            prompt += f"\nTài liệu tham khảo:\n{context}\n"

        guidance = self._part_explanation_guidance(part)
        if guidance:
            prompt += f"\n{guidance}\n\n"

        prompt += (
            "Hãy giải thích:\n"
            "1. Tại sao đáp án đúng là như vậy\n"
            "2. Tại sao đáp án của học sinh sai (nếu sai)\n"
            "3. Mẹo ghi nhớ hoặc quy tắc liên quan\n"
            "Dùng giọng văn thân thiện kiểu 'thầy cô Việt', có ví dụ đời thường."
        )

        explain_system = (
            "Bạn là thầy giáo tiếng Anh Việt Nam, giải thích dễ hiểu, thân thiện. "
            "Khi được cung cấp tài liệu tham khảo, hãy dựa vào đó để giải thích chính xác hơn."
        )
        return await self._call_llm(
            prompt, max_tokens=1000, system_msg=explain_system, provider_override=llm_provider,
            temperature=0.3, task="explain_answer",
        )


    async def translate(
        self,
        text: str,
        direction: str,
        level: str,
        rag_context: str = "",
        *,
        llm_provider: str | None = None,
    ) -> dict:
        """Dịch thuật EN<->VI với giải thích ngữ pháp và từ vựng."""
        if direction == "en_to_vi":
            src, tgt = "tiếng Anh", "tiếng Việt"
        else:
            src, tgt = "tiếng Việt", "tiếng Anh"

        prompt = (
            f"Bạn là trợ lý dịch thuật chuyên nghiệp, dịch từ {src} sang {tgt}.\n"
            f"Trình độ người học: {level}.\n\n"
            f"Văn bản cần dịch:\n\"\"\"\n{text}\n\"\"\"\n\n"
        )

        if rag_context:
            prompt += f"Tài liệu tham khảo ngữ pháp/từ vựng:\n{rag_context}\n\n"

        prompt += (
            "Trả về JSON với format:\n"
            "{\n"
            '  "translated": "bản dịch chính xác, tự nhiên",\n'
            '  "vocabulary": [\n'
            '    {"word": "từ/cụm từ gốc", "meaning": "nghĩa", "example": "ví dụ câu"}\n'
            "  ],\n"
            '  "grammar_notes": [\n'
            '    "Ghi chú ngữ pháp quan trọng trong câu (nếu có)"\n'
            "  ]\n"
            "}\n\n"
            "Yêu cầu:\n"
            "- Dịch chính xác, tự nhiên, không dịch máy\n"
            "- Liệt kê 3-5 từ vựng quan trọng/khó với ví dụ\n"
            "- Ghi chú 1-3 điểm ngữ pháp đáng chú ý\n"
            "- Giải thích bằng tiếng Việt, thân thiện\n"
            "- Chỉ trả về JSON, không thêm text."
        )

        try:
            obj = await self._generate_structured(
                prompt, TranslationResult, validate_translation,
                task="translate", max_tokens=2000, temperature=0.3,
                provider_override=llm_provider,
            )
            return obj.model_dump()
        except StructuredOutputError as e:
            logger.warning("Translate structured output failed: {}", e.errors[:3])
            raw = await self._call_llm(
                prompt, max_tokens=2000, provider_override=llm_provider,
                temperature=0.3, task="translate_fallback",
            )
            return {"translated": raw, "vocabulary": [], "grammar_notes": []}

    CHAT_HISTORY_WINDOW = 10

    @staticmethod
    def _chat_messages(message: str, history: list[dict], rag_context: str) -> list[dict]:
        system_content = (
            "Bạn là trợ lý AI luyện thi TOEIC/IELTS tại Việt Nam. "
            "Trả lời thân thiện, dễ hiểu, theo phong cách thầy cô Việt. "
            "Khi được cung cấp tài liệu tham khảo, hãy dựa vào đó để trả lời chính xác. "
            "Nếu không có thông tin trong tài liệu, vẫn trả lời dựa trên kiến thức của bạn."
        )
        if rag_context:
            system_content += f"\n\nTài liệu tham khảo:\n---\n{rag_context}\n---"
        messages = [{"role": "system", "content": system_content}]
        for h in history[-LLMService.CHAT_HISTORY_WINDOW:]:
            if h.get("role") in ("user", "assistant") and h.get("content"):
                messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": message})
        return messages

    def ensure_configured(self) -> None:
        """Ném LLMNotConfiguredError sớm (trước khi mở stream)."""
        if not self._use_finetuned:
            self._client_and_model  # noqa: B018 - property raises when missing

    async def chat(
        self,
        message: str,
        history: list[dict],
        rag_context: str = "",
        *,
        llm_provider: str | None = None,
    ) -> str:
        """Chat với RAG context. Dùng knowledge base để trả lời câu hỏi ngữ pháp/từ vựng TOEIC/IELTS."""
        messages = self._chat_messages(message, history, rag_context)

        if self._use_finetuned:
            prompt = "\n".join(
                f"{'User' if m['role']=='user' else 'Assistant'}: {m['content']}"
                for m in messages[1:]
            )
            async with llm_span("chat", get_settings().hf_model_name):
                return await self._call_finetuned(
                    prompt, max_tokens=1500, system_msg=messages[0]["content"], provider_override=llm_provider
                )

        client, model = self._client_and_model
        async with llm_span("chat", model) as span:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=1500,
                **self._sampling(0.7),
            )
            span.add_usage(getattr(response, "usage", None))
            return response.choices[0].message.content

    async def chat_stream(
        self,
        message: str,
        history: list[dict],
        rag_context: str = "",
        *,
        llm_provider: str | None = None,
    ):
        """Như chat() nhưng trả về từng đoạn text (async generator)."""
        if self._use_finetuned:
            yield await self.chat(message, history, rag_context, llm_provider=llm_provider)
            return

        messages = self._chat_messages(message, history, rag_context)
        client, model = self._client_and_model
        async with llm_span("chat_stream", model):
            stream = await client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=1500,
                stream=True,
                **self._sampling(0.7),
            )
            async for chunk in stream:
                choices = getattr(chunk, "choices", None) or []
                if not choices:
                    continue
                delta = getattr(choices[0].delta, "content", None)
                if delta:
                    yield delta

llm_service = LLMService()
