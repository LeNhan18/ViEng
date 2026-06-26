from openai import AsyncOpenAI
from groq import AsyncGroq
from app.core.config import get_settings
from app.models.schemas import Skill, Level, ExamType, ToeicReadingPart
from app.services.rag_service import rag_service
from loguru import logger
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch
import random

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
        self._openrouter_client = None
        self._hf_model = None
        self._hf_tokenizer = None

        if settings.use_finetuned_model and settings.hf_model_name:
            logger.info(
                f"Sẽ dùng fine-tuned model: {settings.hf_model_name} (provider={settings.llm_provider})"
            )
        if settings.openrouter_api_key:
            self._openrouter_client = AsyncOpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=settings.openrouter_api_key,
            )

    def _provider(self, override: str | None = None) -> str:
        settings = get_settings()
        p = (override or settings.llm_provider or "auto").strip().lower()
        if p not in ("auto", "openrouter", "hf_inference", "hf_local"):
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

        client = InferenceClient(model=settings.hf_model_name, token=(settings.hf_token or None))

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
        if self._openrouter_client:
            return self._openrouter_client, "openai/gpt-4o-mini"
        raise RuntimeError(
            "Chưa cấu hình API key. Thêm OPENROUTER_API_KEY vào .env"
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
    ) -> str:
        sys_content = system_msg or SYSTEM_PROMPT
        temp = temperature if temperature is not None else round(random.uniform(0.75, 0.9), 2)
        logger.info(f"Using temperature = {temp} for question/response generation")
        
        if self._use_finetuned:
            return await self._call_finetuned(
                prompt, max_tokens=max_tokens, system_msg=sys_content, provider_override=provider_override, temperature=temp
            )

        provider = self._provider(provider_override)
        if provider == "openrouter" and self._openrouter_client:
            client, model = self._openrouter_client, "openai/gpt-4o-mini"
        else:
            client, model = self._client_and_model
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": sys_content},
                {"role": "user", "content": prompt},
            ],
            temperature=temp,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content

    async def generate_questions(
        self,
        exam_type: ExamType,
        skill: Skill,
        level: Level,
        num_questions: int,
        part: ToeicReadingPart | None = None,
        *,
        llm_provider: str | None = None,
    ) -> str:
        logger.info(f"Generating questions: {exam_type}/{skill}/{level} part={part} n={num_questions}")

        selected_grammar = random.choice(GRAMMAR_TOPICS)
        selected_business = random.choice(BUSINESS_TOPICS)
        logger.info(f"Selected random grammar topic: {selected_grammar}")
        logger.info(f"Selected random business topic: {selected_business}")

        random_temp = round(random.uniform(0.75, 0.9), 2)

        if exam_type == ExamType.TOEIC and skill == Skill.READING and part:
            extra_query = f"{selected_grammar} {selected_business}"
            rag_context = self._retrieve_for_part(part.value, level, extra_query)
            if rag_context:
                logger.info(f"RAG context retrieved for {part.value} ({len(rag_context)} chars)")

            if part == ToeicReadingPart.PART5:
                prompt = self._build_part5_prompt(level, num_questions, rag_context, selected_grammar, selected_business)
                return await self._call_llm(prompt, max_tokens=2000, provider_override=llm_provider, temperature=random_temp)

            elif part == ToeicReadingPart.PART6:
                num_passages = max(1, num_questions // 4)
                prompt = self._build_part6_prompt(level, num_passages, rag_context, selected_grammar, selected_business)
                return await self._call_llm(prompt, max_tokens=3000, provider_override=llm_provider, temperature=random_temp)

            elif part == ToeicReadingPart.PART7_SINGLE:
                num_passages = max(1, num_questions // 3)
                prompt = self._build_part7_single_prompt(level, num_passages, rag_context, selected_grammar, selected_business)
                return await self._call_llm(prompt, max_tokens=4000, provider_override=llm_provider, temperature=random_temp)

            elif part == ToeicReadingPart.PART7_MULTIPLE:
                num_sets = max(1, num_questions // 5)
                prompt = self._build_part7_multiple_prompt(level, num_sets, rag_context, selected_grammar, selected_business)
                return await self._call_llm(prompt, max_tokens=4000, provider_override=llm_provider, temperature=random_temp)

        rag_context = rag_service.retrieve_mmr(
            f"{exam_type.value} grammar vocabulary {skill.value} {level.value} {selected_grammar} {selected_business}", k=2,
        )
        rag_section = self._build_rag_context_section(rag_context)

        prompt = (
            f"Bạn là một giáo viên luyện thi {exam_type.value.upper()} giàu kinh nghiệm tại Việt Nam.\n"
            f"Hãy tạo {num_questions} câu hỏi {skill.value} trình độ {level.value}.\n"
            f"Chủ đề ngữ pháp cần tập trung: {selected_grammar}.\n"
            f"Bối cảnh câu hỏi: {selected_business}.\n\n"
            f"Yêu cầu:\n"
            f"- Mỗi câu hỏi có 4 đáp án A, B, C, D (nếu là reading/listening)\n"
            f"- Đánh dấu đáp án đúng\n"
            f"- Nội dung sát format thi {exam_type.value.upper()} thật\n"
            f"{rag_section}\n"
            f"- Trả về JSON array với format:\n"
            f'  [{{"id": 1, "content": "...", "options": ["A. ...", "B. ...", "C. ...", "D. ..."], "correct_answer": "A"}}]\n'
            f"- Chỉ trả về JSON, không thêm text khác."
        )
        return await self._call_llm(prompt, provider_override=llm_provider, temperature=random_temp)

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
            prompt, max_tokens=1000, system_msg=explain_system, provider_override=llm_provider
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

        raw = await self._call_llm(prompt, max_tokens=2000, provider_override=llm_provider)

        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
            import json
            return json.loads(cleaned)
        except Exception:
            return {
                "translated": raw,
                "vocabulary": [],
                "grammar_notes": [],
            }

    async def chat(
        self,
        message: str,
        history: list[dict],
        rag_context: str = "",
        *,
        llm_provider: str | None = None,
    ) -> str:
        """Chat với RAG context. Dùng knowledge base để trả lời câu hỏi ngữ pháp/từ vựng TOEIC/IELTS."""
        system_content = (
            "Bạn là trợ lý AI luyện thi TOEIC/IELTS tại Việt Nam. "
            "Trả lời thân thiện, dễ hiểu, theo phong cách thầy cô Việt. "
            "Khi được cung cấp tài liệu tham khảo, hãy dựa vào đó để trả lời chính xác. "
            "Nếu không có thông tin trong tài liệu, vẫn trả lời dựa trên kiến thức của bạn."
        )
        if rag_context:
            system_content += f"\n\nTài liệu tham khảo:\n---\n{rag_context}\n---"

        messages = [{"role": "system", "content": system_content}]
        for h in history[-10:]:
            messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": message})

        if self._use_finetuned:
            prompt = "\n".join(
                f"{'User' if m['role']=='user' else 'Assistant'}: {m['content']}"
                for m in messages[1:]
            )
            return await self._call_finetuned(
                prompt, max_tokens=1500, system_msg=system_content, provider_override=llm_provider
            )

        provider = self._provider(llm_provider)
        if provider == "openrouter" and self._openrouter_client:
            client, model = self._openrouter_client, "openai/gpt-4o-mini"
        else:
            client, model = self._client_and_model
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            max_tokens=1500,
        )
        return response.choices[0].message.content


llm_service = LLMService()
