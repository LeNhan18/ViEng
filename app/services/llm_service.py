from openai import AsyncOpenAI
from groq import AsyncGroq
from app.core.config import get_settings
from app.models.schemas import Skill, Level, ExamType
from loguru import logger


class LLMService:
    """Quản lý tương tác với LLM (OpenAI/Groq) để tạo câu hỏi và giải thích."""

    def __init__(self):
        settings = get_settings()
        self._openai_client = None
        self._groq_client = None

        if settings.openai_api_key:
            self._openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
        if settings.groq_api_key:
            self._groq_client = AsyncGroq(api_key=settings.groq_api_key)

    @property
    def _client_and_model(self) -> tuple:
        if self._groq_client:
            return self._groq_client, "llama-3.3-70b-versatile"
        if self._openai_client:
            return self._openai_client, "gpt-4o-mini"
        raise RuntimeError(
            "Chưa cấu hình API key. Thêm OPENAI_API_KEY hoặc GROQ_API_KEY vào .env"
        )

    async def generate_questions(
        self,
        exam_type: ExamType,
        skill: Skill,
        level: Level,
        num_questions: int,
    ) -> str:
        client, model = self._client_and_model

        prompt = (
            f"Bạn là một giáo viên luyện thi {exam_type.value.upper()} giàu kinh nghiệm tại Việt Nam.\n"
            f"Hãy tạo {num_questions} câu hỏi {skill.value} trình độ {level.value}.\n\n"
            f"Yêu cầu:\n"
            f"- Mỗi câu hỏi có 4 đáp án A, B, C, D (nếu là reading/listening)\n"
            f"- Đánh dấu đáp án đúng\n"
            f"- Nội dung sát format thi {exam_type.value.upper()} thật\n"
            f"- Trả về JSON array với format:\n"
            f'  [{{"id": 1, "content": "...", "options": ["A. ...", "B. ...", "C. ...", "D. ..."], "correct_answer": "A"}}]\n'
            f"- Chỉ trả về JSON, không thêm text khác."
        )

        logger.info(f"Generating {num_questions} questions: {exam_type}/{skill}/{level}")
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Bạn là trợ lý tạo đề thi tiếng Anh. Luôn trả về JSON hợp lệ."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=2000,
        )

        return response.choices[0].message.content

    async def explain_answer(
        self,
        question: str,
        user_answer: str,
        correct_answer: str,
        context: str = "",
    ) -> str:
        client, model = self._client_and_model

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

        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Bạn là thầy giáo tiếng Anh Việt Nam, giải thích dễ hiểu, thân thiện."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.6,
            max_tokens=1000,
        )

        return response.choices[0].message.content


llm_service = LLMService()
