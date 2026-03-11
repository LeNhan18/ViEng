import json
from fastapi import APIRouter, HTTPException
from app.models.schemas import (
    TestRequest, TestResponse, Question,
    SubmitRequest, SubmitResponse, Feedback,
)
from app.services.llm_service import llm_service
from app.services.rag_service import rag_service
from loguru import logger

router = APIRouter(prefix="/api/v1", tags=["ViEng"])


@router.get("/health")
async def health_check():
    return {"status": "ok", "message": "ViEng API is running"}


@router.post("/test/generate", response_model=TestResponse)
async def generate_test(request: TestRequest):
    """Tạo bài test cá nhân hóa dựa trên kỹ năng và trình độ."""
    try:
        raw = await llm_service.generate_questions(
            exam_type=request.exam_type,
            skill=request.skill,
            level=request.level,
            num_questions=request.num_questions,
        )

        raw_cleaned = raw.strip()
        if raw_cleaned.startswith("```"):
            raw_cleaned = raw_cleaned.split("\n", 1)[1].rsplit("```", 1)[0]

        questions_data = json.loads(raw_cleaned)
        questions = [Question(**q) for q in questions_data]

        return TestResponse(
            exam_type=request.exam_type,
            skill=request.skill,
            level=request.level,
            questions=questions,
        )
    except json.JSONDecodeError:
        logger.error(f"LLM returned invalid JSON: {raw[:200]}")
        raise HTTPException(status_code=502, detail="LLM trả về dữ liệu không hợp lệ. Vui lòng thử lại.")
    except Exception as e:
        logger.error(f"Error generating test: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test/submit", response_model=SubmitResponse)
async def submit_answers(request: SubmitRequest):
    """Chấm bài và trả về feedback chi tiết với giải thích kiểu 'thầy cô Việt'."""
    try:
        feedbacks = []
        correct_count = 0

        for answer in request.answers:
            context = rag_service.retrieve(
                f"{request.exam_type.value} {request.skill.value} question {answer.question_id}"
            )

            explanation = await llm_service.explain_answer(
                question=f"Câu {answer.question_id}",
                user_answer=answer.user_answer,
                correct_answer="",
                context=context,
            )

            is_correct = True  # TODO: so sánh với đáp án đúng từ DB/cache
            if is_correct:
                correct_count += 1

            sources = []
            if context:
                sources = [
                    line.replace("[Nguồn: ", "").replace("]", "")
                    for line in context.split("\n")
                    if line.startswith("[Nguồn:")
                ]

            feedbacks.append(Feedback(
                question_id=answer.question_id,
                is_correct=is_correct,
                user_answer=answer.user_answer,
                correct_answer="",
                explanation=explanation,
                sources=sources,
            ))

        total = len(request.answers)
        return SubmitResponse(
            score=correct_count,
            total=total,
            percentage=round(correct_count / total * 100, 1) if total > 0 else 0,
            feedbacks=feedbacks,
        )
    except Exception as e:
        logger.error(f"Error submitting answers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rag/index")
async def index_knowledge_base():
    """Index lại toàn bộ knowledge base vào vectorstore."""
    count = rag_service.index_knowledge_base()
    if count == 0:
        return {"message": "Không tìm thấy tài liệu. Thêm file .txt vào data/knowledge_base/"}
    return {"message": f"Đã index {count} chunks vào vectorstore"}


@router.post("/rag/search")
async def search_knowledge(query: str):
    """Tìm kiếm trong knowledge base."""
    context = rag_service.retrieve(query)
    if not context:
        return {"results": [], "message": "Không tìm thấy kết quả hoặc vectorstore chưa được tạo."}
    return {"results": context}
