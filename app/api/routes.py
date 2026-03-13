import json
from fastapi import APIRouter, HTTPException
from app.models.schemas import (
    TestRequest, TestResponse, Question,
    Part6Passage, Part7Passage, ToeicReadingSection,
    ToeicReadingPart,
    SubmitRequest, SubmitResponse, Feedback,
    ExamType, Skill,
)
from app.services.llm_service import llm_service
from app.services.rag_service import rag_service
from loguru import logger

router = APIRouter(prefix="/api/v1", tags=["ViEng"])


def _clean_json(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return text


@router.get("/health")
async def health_check():
    return {"status": "ok", "message": "ViEng API is running"}


@router.post("/test/generate", response_model=TestResponse)
async def generate_test(request: TestRequest):
    """Tạo bài test TOEIC/IELTS. Nếu chọn TOEIC Reading + part, sẽ sinh đúng format Part 5/6/7."""
    try:
        is_toeic_reading = (
            request.exam_type == ExamType.TOEIC
            and request.skill == Skill.READING
            and request.part is not None
        )

        raw = await llm_service.generate_questions(
            exam_type=request.exam_type,
            skill=request.skill,
            level=request.level,
            num_questions=request.num_questions,
            part=request.part,
        )

        raw_cleaned = _clean_json(raw)
        data = json.loads(raw_cleaned)

        if is_toeic_reading and request.part == ToeicReadingPart.PART5:
            questions = [Question(**q) for q in data]
            section = ToeicReadingSection(part5=questions)
            return TestResponse(
                exam_type=request.exam_type,
                skill=request.skill,
                level=request.level,
                part=request.part,
                reading_section=section,
                questions=questions,
            )

        if is_toeic_reading and request.part == ToeicReadingPart.PART6:
            passages = [Part6Passage(**p) for p in data]
            all_questions = []
            qid = 1
            for p in passages:
                for q in p.questions:
                    q.id = qid
                    all_questions.append(q)
                    qid += 1
            section = ToeicReadingSection(part6=passages)
            return TestResponse(
                exam_type=request.exam_type,
                skill=request.skill,
                level=request.level,
                part=request.part,
                reading_section=section,
                questions=all_questions,
            )

        if is_toeic_reading and request.part in (
            ToeicReadingPart.PART7_SINGLE,
            ToeicReadingPart.PART7_MULTIPLE,
        ):
            passages = [Part7Passage(**p) for p in data]
            all_questions = []
            qid = 1
            for p in passages:
                for q in p.questions:
                    q.id = qid
                    all_questions.append(q)
                    qid += 1
            section = ToeicReadingSection()
            if request.part == ToeicReadingPart.PART7_SINGLE:
                section.part7_single = passages
            else:
                section.part7_multiple = passages
            return TestResponse(
                exam_type=request.exam_type,
                skill=request.skill,
                level=request.level,
                part=request.part,
                reading_section=section,
                questions=all_questions,
            )

        questions = [Question(**q) for q in data]
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
