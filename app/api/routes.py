import json
import re
from pathlib import Path
from fastapi import APIRouter, HTTPException
from app.models.schemas import (
    TestRequest, TestResponse, Question,
    Part6Passage, Part7Passage, ToeicReadingSection,
    ToeicReadingPart,
    SubmitRequest, SubmitResponse, Feedback,
    TranslateRequest, TranslateResponse,
    ChatRequest, ChatResponse,
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

        part_value = request.part.value if request.part else None

        for answer in request.answers:
            is_correct = (
                answer.user_answer == answer.correct_answer
                or answer.user_answer.startswith(answer.correct_answer)
            )
            if is_correct:
                correct_count += 1

            question_text = answer.question_content or f"Câu {answer.question_id}"
            options_text = ", ".join(answer.options) if answer.options else ""

            rag_query = f"{question_text} {options_text}"
            if answer.passage:
                rag_query = f"{answer.passage[:300]} {rag_query}"
            context = rag_service.retrieve(rag_query, k=3)

            explanation = await llm_service.explain_answer(
                question=f"{question_text}\nĐáp án: {options_text}" if options_text else question_text,
                user_answer=answer.user_answer,
                correct_answer=answer.correct_answer,
                context=context,
                part=part_value,
                passage=answer.passage or "",
            )

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
                correct_answer=answer.correct_answer,
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


@router.post("/translate", response_model=TranslateResponse)
async def translate_text(request: TranslateRequest):
    """Dịch thuật EN<->VI bằng AI, kết hợp RAG để tra cứu ngữ pháp/từ vựng liên quan."""
    try:
        rag_context = ""
        if request.use_rag:
            query = request.text[:200]
            if request.direction.value == "en_to_vi":
                query = f"grammar vocabulary {query}"
            rag_context = rag_service.retrieve(query, k=3)

        result = await llm_service.translate(
            text=request.text,
            direction=request.direction.value,
            level=request.level.value,
            rag_context=rag_context,
        )

        return TranslateResponse(
            original=request.text,
            translated=result.get("translated", ""),
            direction=request.direction,
            vocabulary=result.get("vocabulary", []),
            grammar_notes=result.get("grammar_notes", []),
            rag_context=rag_context[:500] if rag_context else "",
        )
    except Exception as e:
        logger.error(f"Error translating: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Chatbot RAG + LLM: trả lời câu hỏi ngữ pháp/từ vựng TOEIC/IELTS dựa trên knowledge base."""
    try:
        rag_context = rag_service.retrieve_mmr(request.message, k=4, fetch_k=10)
        sources = []
        for m in re.finditer(r"\[Nguồn: ([^\]]+)\]", rag_context or ""):
            p = m.group(1).strip()
            name = Path(p).name if "/" in p or "\\" in p else p
            if name and name not in sources:
                sources.append(name)
        sources = sources[:5]

        history = [{"role": h.role, "content": h.content} for h in request.history]
        reply = await llm_service.chat(
            message=request.message,
            history=history,
            rag_context=rag_context,
        )
        return ChatResponse(message=reply, sources=sources)
    except Exception as e:
        logger.error(f"Error in chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rag/index")
async def index_knowledge_base():
    """Index lại toàn bộ knowledge base vào vectorstore."""
    count = rag_service.index_knowledge_base()
    if count == 0:
        return {"message": "Không tìm thấy tài liệu. Thêm file .txt vào data/knowledge_base/"}
    return {"message": f"Đã index {count} chunks vào vectorstore"}


@router.get("/rag/list")
async def list_vectorstore(limit: int = 20, offset: int = 0):
    """Liệt kê các chunks trong vectorstore (để xem nội dung đã index)."""
    try:
        vs = rag_service._get_vectorstore()
        if vs is None:
            return {"chunks": [], "total": 0, "message": "Vectorstore chưa được tạo."}
        collection = vs._collection
        data = collection.get(include=["documents", "metadatas"])
        docs = data.get("documents") or []
        metas = data.get("metadatas") or [{}] * len(docs)
        total = len(docs)
        chunks = []
        for i, (d, m) in enumerate(zip(docs[offset : offset + limit], metas[offset : offset + limit])):
            src = m.get("source") or "N/A"
            if isinstance(src, str) and "/" in src:
                src = src.split("/")[-1].split("\\")[-1]
            chunks.append({
                "index": offset + i + 1,
                "source": src,
                "content": d[:500] + "..." if len(d) > 500 else d,
                "length": len(d),
            })
        return {"chunks": chunks, "total": total, "limit": limit, "offset": offset}
    except Exception as e:
        logger.error(f"Error listing vectorstore: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rag/search")
async def search_knowledge(query: str):
    """Tìm kiếm trong knowledge base."""
    context = rag_service.retrieve(query)
    if not context:
        return {"results": [], "message": "Không tìm thấy kết quả hoặc vectorstore chưa được tạo."}
    return {"results": context}
