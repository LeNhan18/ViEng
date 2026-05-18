"""Schema Pydantic khớp API routes và LLM service."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExamType(str, Enum):
    TOEIC = "toeic"
    IELTS = "ielts"


class Skill(str, Enum):
    READING = "reading"
    LISTENING = "listening"
    WRITING = "writing"
    SPEAKING = "speaking"


class Level(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class ToeicReadingPart(str, Enum):
    PART5 = "part5"
    PART6 = "part6"
    PART7_SINGLE = "part7_single"
    PART7_MULTIPLE = "part7_multiple"


class TranslateDirection(str, Enum):
    EN_TO_VI = "en_to_vi"
    VI_TO_EN = "vi_to_en"


class Question(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    content: str
    options: list[str] = Field(default_factory=list)
    correct_answer: str


class Part6Passage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    passage: str
    questions: list[Question]


class Part7Passage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    passages: list[str]
    questions: list[Question]


class ToeicReadingSection(BaseModel):
    model_config = ConfigDict(extra="ignore")

    part5: list[Question] | None = None
    part6: list[Part6Passage] | None = None
    part7_single: list[Part7Passage] | None = None
    part7_multiple: list[Part7Passage] | None = None


class TestRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    exam_type: ExamType
    skill: Skill
    level: Level
    num_questions: int = Field(ge=1, le=200)
    part: ToeicReadingPart | None = None
    llm_provider: str | None = None


class TestResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    exam_type: ExamType
    skill: Skill
    level: Level
    part: ToeicReadingPart | None = None
    reading_section: ToeicReadingSection | None = None
    questions: list[Question] = Field(default_factory=list)


class AnswerSubmission(BaseModel):
    model_config = ConfigDict(extra="ignore")

    question_id: int
    user_answer: str
    correct_answer: str
    question_content: str | None = None
    options: list[str] | None = None
    passage: str | None = None


class SubmitRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    answers: list[AnswerSubmission]
    part: ToeicReadingPart | None = None
    # Frontend gửi thêm để nhất quán; backend chưa dùng nhưng chấp nhận body.
    exam_type: ExamType | None = None
    skill: Skill | None = None


class Feedback(BaseModel):
    model_config = ConfigDict(extra="ignore")

    question_id: int
    is_correct: bool
    user_answer: str
    correct_answer: str
    explanation: str
    sources: list[str] = Field(default_factory=list)


class SubmitResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    score: int
    total: int
    percentage: float
    feedbacks: list[Feedback]


class VocabularyItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    word: str = ""
    meaning: str = ""
    example: str = ""


class TranslateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str = Field(min_length=1)
    direction: TranslateDirection
    level: Level
    use_rag: bool = False
    llm_provider: str | None = None


class TranslateResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    original: str
    translated: str
    direction: TranslateDirection
    vocabulary: list[Any] = Field(default_factory=list)
    grammar_notes: list[str] = Field(default_factory=list)
    rag_context: str = ""


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: str
    content: str


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: str = Field(min_length=1)
    history: list[ChatMessage] = Field(default_factory=list)
    llm_provider: str | None = None


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: str
    sources: list[str] = Field(default_factory=list)


class OcrChatResponse(BaseModel):
    """Chat response kèm văn bản OCR đã trích xuất từ file người dùng gửi."""

    model_config = ConfigDict(extra="ignore")

    message: str
    sources: list[str] = Field(default_factory=list)
    extracted_text: str = ""
    file_name: str = ""


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class AuthTokenResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    access_token: str
    token_type: str = "bearer"


class UserMeResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    email: str
    created_at: str | None = None
