from openai import AsyncOpenAI
from groq import AsyncGroq
from app.core.config import get_settings
from app.models.schemas import Skill, Level, ExamType, ToeicReadingPart
from app.services.rag_service import rag_service
from loguru import logger

SYSTEM_PROMPT = (
    "Bạn là giáo viên luyện thi TOEIC/IELTS chuyên nghiệp tại Việt Nam. "
    "Khi được cung cấp tài liệu tham khảo, hãy sử dụng nội dung đó để tạo câu hỏi/giải thích chính xác hơn. "
    "Luôn trả về JSON hợp lệ khi được yêu cầu."
)


class LLMService:
    """Quản lý tương tác với LLM (OpenAI/Groq hoặc fine-tuned model trên HF)."""

    def __init__(self):
        settings = get_settings()
        self._openai_client = None
        self._groq_client = None
        self._hf_model = None
        self._hf_tokenizer = None

        if settings.use_finetuned_model and settings.hf_model_name:
            logger.info(f"Sẽ dùng fine-tuned model: {settings.hf_model_name}")
        if settings.openai_api_key:
            self._openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
        if settings.groq_api_key:
            self._groq_client = AsyncGroq(api_key=settings.groq_api_key)

    def _load_hf_model(self):
        """Lazy-load fine-tuned model từ HuggingFace (chỉ gọi khi cần)."""
        if self._hf_model is not None:
            return

        settings = get_settings()
        logger.info(f"Loading fine-tuned model: {settings.hf_model_name}")

        try:
            from transformers import AutoTokenizer, AutoModelForCausalLM
            import torch

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

    async def _generate_with_hf(self, prompt: str, max_tokens: int = 1000, system_msg: str = "") -> str:
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
                temperature=0.7,
                do_sample=True,
            )

        return self._hf_tokenizer.decode(outputs[0][inputs.shape[-1]:], skip_special_tokens=True)

    @property
    def _client_and_model(self) -> tuple:
        if self._groq_client:
            return self._groq_client, "llama-3.3-70b-versatile"
        if self._openai_client:
            return self._openai_client, "gpt-4o-mini"
        raise RuntimeError(
            "Chưa cấu hình API key. Thêm OPENAI_API_KEY hoặc GROQ_API_KEY vào .env"
        )

    @property
    def _use_finetuned(self) -> bool:
        settings = get_settings()
        return settings.use_finetuned_model and settings.hf_model_name

    def _build_rag_context_section(self, rag_context: str) -> str:
        """Tạo đoạn RAG context để chèn vào prompt."""
        if not rag_context:
            return ""
        return (
            "\n\nTài liệu tham khảo ngữ pháp/từ vựng (dùng để tạo câu hỏi chính xác hơn):\n"
            f"---\n{rag_context}\n---\n"
        )

    def _retrieve_for_part(self, part: str, level: Level) -> str:
        """Retrieve RAG context phù hợp cho từng dạng Part."""
        queries = {
            "part5": f"TOEIC Part 5 grammar rules word forms tenses prepositions {level.value}",
            "part6": f"TOEIC Part 6 connectors conjunctions text completion grammar {level.value}",
            "part7_single": f"TOEIC Part 7 reading comprehension vocabulary business {level.value}",
            "part7_multiple": f"TOEIC Part 7 multiple passages vocabulary business communication {level.value}",
        }
        query = queries.get(part, f"TOEIC grammar vocabulary {level.value}")
        return rag_service.retrieve_mmr(query, k=3)

    def _build_part5_prompt(self, level: Level, num_questions: int, rag_context: str = "") -> str:
        base = (
            f"Tạo {num_questions} câu hỏi TOEIC Reading Part 5 (Incomplete Sentences) trình độ {level.value}.\n\n"
            "Format chuẩn TOEIC Part 5:\n"
            "- Mỗi câu là 1 câu tiếng Anh có 1 chỗ trống (___)\n"
            "- 4 đáp án A, B, C, D\n"
            "- Kiểm tra ngữ pháp (thì, dạng từ, giới từ, mệnh đề quan hệ...) hoặc từ vựng\n"
            "- Chủ đề: công việc, email, hợp đồng, kinh doanh\n"
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

    def _build_part6_prompt(self, level: Level, num_passages: int, rag_context: str = "") -> str:
        base = (
            f"Tạo {num_passages} đoạn văn TOEIC Reading Part 6 (Text Completion) trình độ {level.value}.\n\n"
            "Format chuẩn TOEIC Part 6:\n"
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

    def _build_part7_single_prompt(self, level: Level, num_passages: int, rag_context: str = "") -> str:
        base = (
            f"Tạo {num_passages} bài đọc TOEIC Reading Part 7 Single Passage trình độ {level.value}.\n\n"
            "Format chuẩn TOEIC Part 7 Single:\n"
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

    def _build_part7_multiple_prompt(self, level: Level, num_sets: int, rag_context: str = "") -> str:
        base = (
            f"Tạo {num_sets} bộ TOEIC Reading Part 7 Multiple Passages trình độ {level.value}.\n\n"
            "Format chuẩn TOEIC Part 7 Multiple:\n"
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

    async def _call_llm(self, prompt: str, max_tokens: int = 2000, system_msg: str = "") -> str:
        sys_content = system_msg or SYSTEM_PROMPT
        if self._use_finetuned:
            return await self._generate_with_hf(prompt, max_tokens=max_tokens, system_msg=sys_content)

        client, model = self._client_and_model
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": sys_content},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
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
    ) -> str:
        logger.info(f"Generating questions: {exam_type}/{skill}/{level} part={part} n={num_questions}")

        if exam_type == ExamType.TOEIC and skill == Skill.READING and part:
            rag_context = self._retrieve_for_part(part.value, level)
            if rag_context:
                logger.info(f"RAG context retrieved for {part.value} ({len(rag_context)} chars)")

            if part == ToeicReadingPart.PART5:
                prompt = self._build_part5_prompt(level, num_questions, rag_context)
                return await self._call_llm(prompt, max_tokens=2000)

            elif part == ToeicReadingPart.PART6:
                num_passages = max(1, num_questions // 4)
                prompt = self._build_part6_prompt(level, num_passages, rag_context)
                return await self._call_llm(prompt, max_tokens=3000)

            elif part == ToeicReadingPart.PART7_SINGLE:
                num_passages = max(1, num_questions // 3)
                prompt = self._build_part7_single_prompt(level, num_passages, rag_context)
                return await self._call_llm(prompt, max_tokens=4000)

            elif part == ToeicReadingPart.PART7_MULTIPLE:
                num_sets = max(1, num_questions // 5)
                prompt = self._build_part7_multiple_prompt(level, num_sets, rag_context)
                return await self._call_llm(prompt, max_tokens=4000)

        rag_context = rag_service.retrieve_mmr(
            f"TOEIC IELTS grammar vocabulary {skill.value} {level.value}", k=2,
        )
        rag_section = self._build_rag_context_section(rag_context)

        prompt = (
            f"Bạn là một giáo viên luyện thi {exam_type.value.upper()} giàu kinh nghiệm tại Việt Nam.\n"
            f"Hãy tạo {num_questions} câu hỏi {skill.value} trình độ {level.value}.\n\n"
            f"Yêu cầu:\n"
            f"- Mỗi câu hỏi có 4 đáp án A, B, C, D (nếu là reading/listening)\n"
            f"- Đánh dấu đáp án đúng\n"
            f"- Nội dung sát format thi {exam_type.value.upper()} thật\n"
            f"{rag_section}\n"
            f"- Trả về JSON array với format:\n"
            f'  [{{"id": 1, "content": "...", "options": ["A. ...", "B. ...", "C. ...", "D. ..."], "correct_answer": "A"}}]\n'
            f"- Chỉ trả về JSON, không thêm text khác."
        )
        return await self._call_llm(prompt)

    async def explain_answer(
        self,
        question: str,
        user_answer: str,
        correct_answer: str,
        context: str = "",
    ) -> str:
        prompt = (
            f"Bạn là thầy giáo tiếng Anh Việt Nam, giải thích thân thiện, gần gũi.\n\n"
            f"Câu hỏi: {question}\n"
            f"Đáp án của học sinh: {user_answer}\n"
            f"Đáp án đúng: {correct_answer}\n"
        )
        if context:
            prompt += f"\nTài liệu tham khảo:\n{context}\n"

        prompt += (
            "\nHãy giải thích:\n"
            "1. Tại sao đáp án đúng là như vậy\n"
            "2. Tại sao đáp án của học sinh sai (nếu sai)\n"
            "3. Mẹo ghi nhớ hoặc quy tắc liên quan\n"
            "Dùng giọng văn thân thiện kiểu 'thầy cô Việt', có ví dụ đời thường."
        )

        explain_system = (
            "Bạn là thầy giáo tiếng Anh Việt Nam, giải thích dễ hiểu, thân thiện. "
            "Khi được cung cấp tài liệu tham khảo, hãy dựa vào đó để giải thích chính xác hơn."
        )
        return await self._call_llm(prompt, max_tokens=1000, system_msg=explain_system)


    async def translate(
        self,
        text: str,
        direction: str,
        level: str,
        rag_context: str = "",
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

        raw = await self._call_llm(prompt, max_tokens=2000)

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


llm_service = LLMService()
