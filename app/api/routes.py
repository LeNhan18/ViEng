import json
import re
import secrets
from pathlib import Path
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.schemas import (
    TestRequest, TestResponse, Question,
    Part6Passage, Part7Passage, ToeicReadingSection,
    ToeicReadingPart,
    SubmitRequest, SubmitResponse, Feedback,
    TranslateRequest, TranslateResponse,
    ChatRequest, ChatResponse, OcrChatResponse, ChatMessage,
    ExamType, Skill,
    RegisterRequest, LoginRequest, AuthTokenResponse, UserMeResponse,
)
from app.db.database import get_db
from app.models.orm import User
from app.services.llm_service import LLMNotConfiguredError, llm_service
from app.services.ocr_service import OCRError, ocr_service
from app.services.rag_metadata import evidence_snippet
from app.services.rag_service import RagStatus, rag_service
from app.services.structured import StructuredOutputError
from app.core.observability import stats as obs_stats
from app.services.chat_memory_service import chat_memory_service
from app.services.auth_service import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.core.config import get_settings
from loguru import logger

router = APIRouter(prefix="/api/v1", tags=["ViEng"])

_INTERNAL_ERROR = (
    "Đã xảy ra lỗi hệ thống. "
    "Vui lòng thử lại sau."
)


def _clean_json(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return text


@router.get("/health")
async def health_check():
    return {"status": "ok", "message": "ViEng API is running"}


@router.get("/health/ready")
async def readiness_check():
    """Readiness cho k8s/Docker: phản ánh tình trạng embedding/index của RAG.

    RAG tắt chủ động (RAG_ENABLED=false) vẫn là ready — app chạy ở chế độ lite.
    RAG bật nhưng embedder/index chưa sẵn sàng thì trả 503 kèm lý do cụ thể,
    thay vì "ok" giả rồi mọi câu trả lời đều thiếu căn cứ.
    """
    rag = rag_service.status()
    lite_mode = not rag["enabled"]
    ready = lite_mode or bool(rag["ready"])
    body = {
        "status": "ready" if ready else "not_ready",
        "mode": "lite" if lite_mode else "rag",
        "checks": {
            "rag": {
                "status": rag["status"],
                "embedder": rag["embedder"],
                "index_present": rag["index"]["present"],
                "index_version": rag["index"].get("version", ""),
                # Lý do chính đáng duy nhất khiến index có mặt nhưng không dùng
                # được: nó được build bằng cấu hình embedding khác. Thiếu field
                # (index cũ / caller khác) = không kết luận, giống legacy index.
                "index_compatible": rag["index"].get("compatible", True),
                "reason": (
                    rag["index"].get("incompatible_reason")
                    or rag.get("last_error", "")
                ),
            }
        },
    }
    if ready:
        return body
    return JSONResponse(status_code=503, content=body)


_admin_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)


async def _require_admin(admin_key: str | None = Depends(_admin_key_header)) -> None:
    """Chặn các thao tác quản trị index / xem kho tài liệu.

    Fail-closed: ADMIN_API_KEY để trống nghĩa là chưa cấu hình quản trị, và các
    endpoint này bị chặn hoàn toàn — không phải mở cho mọi người.
    """
    expected = (get_settings().admin_api_key or "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail=(
                "Thao tác quản trị chưa được cấu hình (ADMIN_API_KEY trống)."
            ),
        )
    if not admin_key or not secrets.compare_digest(admin_key, expected):
        raise HTTPException(status_code=403, detail="Yêu cầu khoá quản trị hợp lệ.")


@router.get("/metrics")
async def metrics():
    """Latency p50/p95, tỉ lệ lỗi, token, số lần tự sửa theo task LLM và theo route HTTP."""
    return obs_stats.snapshot()


_bearer = HTTPBearer(auto_error=False)


async def _get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User:
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    try:
        payload = decode_token(creds.credentials)
        user_id = int(payload.get("sub"))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")

    if not get_settings().use_database:
        return User(id=user_id, email="cached_user@example.com")

    from app.db.database import _get_engine_and_sessionmaker
    _, session_factory = _get_engine_and_sessionmaker()
    async with session_factory() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=401, detail="User not found.")
        return user


async def _get_current_user_optional(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User | None:
    if creds is None or not creds.credentials:
        return None
    try:
        payload = decode_token(creds.credentials)
        user_id = int(payload.get("sub"))
    except Exception:
        return None

    if not get_settings().use_database:
        return User(id=user_id, email="cached_user@example.com")

    from app.db.database import _get_engine_and_sessionmaker
    _, session_factory = _get_engine_and_sessionmaker()
    async with session_factory() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        return user


@router.post("/auth/register", response_model=AuthTokenResponse)
async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)):
    email = request.email.strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=400, detail="Email không hợp lệ.")

    exists = await db.execute(select(User).where(User.email == email))
    if exists.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Email đã được sử dụng.")

    user = User(email=email, password_hash=hash_password(request.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return AuthTokenResponse(access_token=create_access_token(user_id=user.id))


@router.post("/auth/login", response_model=AuthTokenResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    email = request.email.strip().lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không đúng.")
    return AuthTokenResponse(access_token=create_access_token(user_id=user.id))


@router.get("/auth/me", response_model=UserMeResponse)
async def me(user: User = Depends(_get_current_user)):
    return UserMeResponse(
        id=user.id,
        email=user.email,
        created_at=user.created_at.isoformat() if getattr(user, "created_at", None) else None,
    )


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
            llm_provider=request.llm_provider,
        )

        # generate_questions trả về dữ liệu đã validate; vẫn chấp nhận chuỗi JSON (tương thích cũ).
        data = json.loads(_clean_json(raw)) if isinstance(raw, str) else raw

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

    except StructuredOutputError as e:
        logger.error("LLM output invalid after repairs: {}", e.errors[:5])
        raise HTTPException(status_code=502, detail="LLM trả về dữ liệu không hợp lệ. Vui lòng thử lại.")
    except json.JSONDecodeError:
        logger.error("LLM returned invalid JSON")
        raise HTTPException(status_code=502, detail="LLM trả về dữ liệu không hợp lệ. Vui lòng thử lại.")
    except LLMNotConfiguredError:
        raise
    except Exception as e:
        logger.exception("Error generating test: {}", e)
        raise HTTPException(status_code=500, detail=_INTERNAL_ERROR)


@router.post("/test/submit", response_model=SubmitResponse)
async def submit_answers(request: SubmitRequest):
    """Chấm bài và trả về feedback chi tiết với giải thích kiểu 'thầy cô Việt'."""
    try:
        import asyncio
        part_value = request.part.value if request.part else None
        sem = asyncio.Semaphore(5)

        async def _one(answer):
            is_correct = (
                answer.user_answer == answer.correct_answer
                or answer.user_answer.startswith(answer.correct_answer)
            )
            question_text = answer.question_content or f"Câu {answer.question_id}"
            options_text = ", ".join(answer.options) if answer.options else ""
            rag_query = f"{question_text} {options_text}"
            if answer.passage:
                rag_query = f"{answer.passage[:300]} {rag_query}"
            async with sem:
                context = await run_in_threadpool(rag_service.retrieve, rag_query, 3)
                explanation = await llm_service.explain_answer(
                    question=f"{question_text}\nĐáp án: {options_text}" if options_text else question_text,
                    user_answer=answer.user_answer,
                    correct_answer=answer.correct_answer,
                    context=context,
                    part=part_value,
                    passage=answer.passage or "",
                )
            sources = [
                line.replace("[Nguồn: ", "").replace("]", "")
                for line in (context or "").split("\n")
                if line.startswith("[Nguồn:")
            ]
            return Feedback(
                question_id=answer.question_id,
                is_correct=is_correct,
                user_answer=answer.user_answer,
                correct_answer=answer.correct_answer,
                explanation=explanation,
                sources=sources,
            )

        feedbacks = await asyncio.gather(*(_one(a) for a in request.answers))
        correct_count = sum(1 for f in feedbacks if f.is_correct)

        total = len(request.answers)
        return SubmitResponse(
            score=correct_count,
            total=total,
            percentage=round(correct_count / total * 100, 1) if total > 0 else 0,
            feedbacks=feedbacks,
        )
    except LLMNotConfiguredError:
        raise
    except Exception as e:
        logger.exception("Error submitting answers: {}", e)
        raise HTTPException(status_code=500, detail=_INTERNAL_ERROR)


@router.post("/tts")
async def text_to_speech(text: str = Body(..., embed=True, min_length=1, max_length=2000)):
    """Chuyển text tiếng Anh thành audio (phát âm) — dùng Edge TTS miễn phí."""
    try:
        import edge_tts
        communicate = edge_tts.Communicate(text.strip(), "en-US-AriaNeural")
        audio_data = bytearray()
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                audio_data.extend(chunk["data"])
        return Response(
            content=bytes(audio_data),
            media_type="audio/mpeg",
            headers={"Content-Disposition": "inline; filename=speech.mp3"},
        )
    except LLMNotConfiguredError:
        raise
    except Exception as e:
        logger.exception("TTS error: {}", e)
        raise HTTPException(status_code=500, detail="Không thể tạo audio. Vui lòng thử lại.")


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
            llm_provider=request.llm_provider,
        )

        return TranslateResponse(
            original=request.text,
            translated=result.get("translated", ""),
            direction=request.direction,
            vocabulary=result.get("vocabulary", []),
            grammar_notes=result.get("grammar_notes", []),
            rag_context=rag_context[:500] if rag_context else "",
        )
    except LLMNotConfiguredError:
        raise
    except Exception as e:
        logger.exception("Error translating: {}", e)
        raise HTTPException(status_code=500, detail=_INTERNAL_ERROR)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    user: User | None = Depends(_get_current_user_optional)
):
    """Chatbot RAG + LLM: trả lời câu hỏi ngữ pháp/từ vựng TOEIC/IELTS dựa trên knowledge base."""
    try:
        settings = get_settings()
        db = None
        db_context = None
        if settings.use_database:
            from app.db.database import _get_engine_and_sessionmaker
            _, session_factory = _get_engine_and_sessionmaker()
            db_context = session_factory()
            db = await db_context.__aenter__()

        try:
            # 1. Tải lịch sử chat từ memory service nếu user đã đăng nhập
            history = []
            if user:
                history = await chat_memory_service.get_history(user.id, db=db)

            # Nếu không có lịch sử trong memory (chưa đăng nhập hoặc là chat đầu tiên), dùng history từ request gửi lên
            if not history:
                history = [{"role": h.role, "content": h.content} for h in request.history]

            # 2. Lưu tin nhắn mới của user vào memory nếu đã đăng nhập
            if user:
                await chat_memory_service.add_message(
                    user_id=user.id,
                    role="user",
                    content=request.message,
                    db=db
                )

            # 3. Truy xuất RAG context
            rag_context = rag_service.retrieve_mmr(request.message, k=4, fetch_k=10)
            sources = []
            for m in re.finditer(r"\[Nguồn: ([^\]]+)\]", rag_context or ""):
                p = m.group(1).strip()
                name = Path(p).name if "/" in p or "\\" in p else p
                if name and name not in sources:
                    sources.append(name)
            sources = sources[:5]

            # 4. Gọi LLM để sinh câu trả lời
            reply = await llm_service.chat(
                message=request.message,
                history=history,
                rag_context=rag_context,
                llm_provider=request.llm_provider,
            )

            # 5. Lưu câu trả lời của AI vào memory nếu đã đăng nhập
            if user:
                await chat_memory_service.add_message(
                    user_id=user.id,
                    role="assistant",
                    content=reply,
                    sources=sources,
                    db=db
                )

            return ChatResponse(message=reply, sources=sources)

        finally:
            if db_context:
                await db_context.__aexit__(None, None, None)

    except LLMNotConfiguredError:
        raise
    except Exception as e:
        logger.exception("Error in chat: {}", e)
        raise HTTPException(status_code=500, detail=_INTERNAL_ERROR)


_OCR_USER_PROMPT_TEMPLATE = (
    "Người dùng đã gửi một {kind} và mong bạn giúp dựa trên nội dung đó.\n"
    "Văn bản trích xuất từ {kind} (có thể có lỗi nhận dạng nhỏ, hãy hiểu theo ngữ cảnh):\n"
    "\"\"\"\n{extracted}\n\"\"\"\n\n"
    "Câu hỏi của người dùng:\n{question}"
)


@router.post("/chat/ocr", response_model=OcrChatResponse)
async def chat_with_ocr(
    file: UploadFile = File(..., description="Ảnh hoặc PDF cần OCR"),
    message: str = Form(
        "",
        description="Câu hỏi/yêu cầu của người dùng. Bỏ trống = tự giải thích nội dung.",
    ),
    llm_provider: str | None = Form(None),
    user: User | None = Depends(_get_current_user_optional),
):
    """Nhận ảnh/PDF, OCR ra văn bản rồi gửi vào pipeline chat (RAG + LLM)."""
    if not ocr_service.enabled:
        raise HTTPException(status_code=503, detail="Tính năng OCR đang bị tắt.")

    try:
        data = await file.read()
    except LLMNotConfiguredError:
        raise
    except Exception as e:
        logger.exception("Error reading uploaded file: {}", e)
        raise HTTPException(status_code=400, detail="Không đọc được file tải lên.")

    if not data:
        raise HTTPException(status_code=400, detail="File rỗng.")
    if len(data) > ocr_service.max_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                f"File vượt quá giới hạn "
                f"{ocr_service.max_bytes // (1024 * 1024)}MB."
            ),
        )

    try:
        extracted = await run_in_threadpool(
            ocr_service.extract_text,
            data,
            content_type=file.content_type,
            filename=file.filename,
        )
    except OCRError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("OCR error: {}", e)
        raise HTTPException(status_code=500, detail=_INTERNAL_ERROR)

    if not extracted.strip():
        raise HTTPException(
            status_code=422,
            detail=(
                "Không nhận diện được văn bản trong file. Hãy thử ảnh rõ nét hơn "
                "hoặc PDF có chữ."
            ),
        )

    user_question = (message or "").strip() or (
        "Hãy giải thích nội dung văn bản trên một cách dễ hiểu, "
        "kèm dịch nghĩa nếu là tiếng Anh và nêu các điểm ngữ pháp/từ vựng quan trọng."
    )
    is_pdf = (file.content_type or "").lower() == "application/pdf" or (
        (file.filename or "").lower().endswith(".pdf")
    )
    composed_message = _OCR_USER_PROMPT_TEMPLATE.format(
        kind="PDF" if is_pdf else "ảnh",
        extracted=extracted,
        question=user_question,
    )

    try:
        # RAG truy vấn theo câu hỏi của user, không cần dùng toàn bộ văn bản OCR.
        rag_context = rag_service.retrieve_mmr(user_question, k=4, fetch_k=10)
        sources: list[str] = []
        for m in re.finditer(r"\[Nguồn: ([^\]]+)\]", rag_context or ""):
            p = m.group(1).strip()
            name = Path(p).name if "/" in p or "\\" in p else p
            if name and name not in sources:
                sources.append(name)
        sources = sources[:5]

        reply = await llm_service.chat(
            message=composed_message,
            history=[],
            rag_context=rag_context,
            llm_provider=llm_provider,
        )

        # Lưu tin nhắn và phản hồi vào memory nếu user đã đăng nhập
        if user:
            settings = get_settings()
            db = None
            db_context = None
            if settings.use_database:
                from app.db.database import _get_engine_and_sessionmaker
                _, session_factory = _get_engine_and_sessionmaker()
                db_context = session_factory()
                db = await db_context.__aenter__()
            try:
                user_msg_content = message.strip() or "(đã gửi file)"
                # Lưu câu hỏi của user
                await chat_memory_service.add_message(
                    user_id=user.id,
                    role="user",
                    content=user_msg_content,
                    db=db
                )
                # Lưu câu trả lời của AI
                await chat_memory_service.add_message(
                    user_id=user.id,
                    role="assistant",
                    content=reply,
                    sources=sources,
                    db=db
                )
            finally:
                if db_context:
                    await db_context.__aexit__(None, None, None)

        return OcrChatResponse(
            message=reply,
            sources=sources,
            extracted_text=extracted,
            file_name=file.filename or "",
        )
    except LLMNotConfiguredError:
        raise
    except Exception as e:
        logger.exception("Error in chat_with_ocr LLM stage: {}", e)
        raise HTTPException(status_code=500, detail=_INTERNAL_ERROR)


@router.post("/ocr", response_model=dict)
async def ocr_only(file: UploadFile = File(...)):
    """Chỉ OCR ra text mà không gọi LLM (hữu ích cho debug hoặc UI hiển thị trước)."""
    if not ocr_service.enabled:
        raise HTTPException(status_code=503, detail="Tính năng OCR đang bị tắt.")
    try:
        data = await file.read()
    except LLMNotConfiguredError:
        raise
    except Exception as e:
        logger.exception("Error reading uploaded file: {}", e)
        raise HTTPException(status_code=400, detail="Không đọc được file tải lên.")
    try:
        extracted = await run_in_threadpool(
            ocr_service.extract_text,
            data,
            content_type=file.content_type,
            filename=file.filename,
        )
    except OCRError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("OCR-only error: {}", e)
        raise HTTPException(status_code=500, detail=_INTERNAL_ERROR)
    return {"file_name": file.filename or "", "extracted_text": extracted}


@router.post("/rag/index", dependencies=[Depends(_require_admin)])
async def index_knowledge_base():
    """Index lại knowledge base: build index mới, verify, rồi swap.

    Chạy trong threadpool vì build embedding là sync và nặng — gọi trực tiếp
    trong endpoint async sẽ block event loop và làm mọi request khác treo.
    Index đang chạy chỉ bị thay khi bản mới verify xong.
    """
    try:
        count = await run_in_threadpool(rag_service.index_knowledge_base)
    except RuntimeError as e:
        # reindex khác đang chạy, hoặc embedder không khả dụng
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.exception("Reindex lỗi: {}", e)
        raise HTTPException(
            status_code=500,
            detail="Reindex thất bại; index cũ được giữ nguyên. Xem log để biết chi tiết.",
        )
    if count == 0:
        return {
            "indexed_chunks": 0,
            "message": "Không tìm thấy tài liệu. Thêm file .txt/.pdf vào data/knowledge_base/",
        }
    return {
        "indexed_chunks": count,
        "message": f"Đã index {count} chunks vào vectorstore",
    }


@router.get("/rag/status", dependencies=[Depends(_require_admin)])
async def rag_status():
    """Trạng thái chi tiết của RAG: embedder, index version, lỗi gần nhất."""
    return rag_service.status()


@router.post("/rag/rollback", dependencies=[Depends(_require_admin)])
async def rag_rollback(version: str = Body("", embed=True)):
    """Quay index về một version cũ (mặc định: bản ngay trước bản đang dùng)."""
    try:
        activated = await run_in_threadpool(rag_service.rollback, version)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"active_version": activated, "message": f"Đã quay về index version {activated}"}


@router.get("/rag/list", dependencies=[Depends(_require_admin)])
async def list_vectorstore(limit: int = 20, offset: int = 0):
    """Liệt kê các chunks trong vectorstore (để xem nội dung đã index)."""
    try:
        vs = rag_service._get_vectorstore()
        if vs is None:
            return {"chunks": [], "total": 0, "message": "Vectorstore chưa được tạo."}
        try:
            collection = vs._collection
            data = collection.get(include=["documents", "metadatas"])
        except Exception as inner:
            logger.warning("Không đọc được collection nội bộ Chroma: {}", inner)
            return {
                "chunks": [],
                "total": 0,
                "message": (
                    "Kh\u00f4ng li\u1ec7t k\u00ea \u0111\u01b0\u1ee3c vectorstore "
                    "(phi\u00ean b\u1ea3n Chroma ho\u1eb7c l\u1ed7i truy c\u1eadp)."
                ),
            }
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
                "doc_id": m.get("doc_id"),
                "chunk_id": m.get("chunk_id"),
                "page": m.get("page"),
                "section": m.get("section") or None,
                "language": m.get("language"),
                "content_hash": m.get("content_hash"),
                "source": src,
                "content": d[:500] + "..." if len(d) > 500 else d,
                "length": len(d),
            })
        return {"chunks": chunks, "total": total, "limit": limit, "offset": offset}
    except LLMNotConfiguredError:
        raise
    except Exception as e:
        logger.exception("Error listing vectorstore: {}", e)
        raise HTTPException(status_code=500, detail=_INTERNAL_ERROR)


_RAG_STATUS_MESSAGES = {
    RagStatus.DISABLED: "RAG đang tắt (RAG_ENABLED=false).",
    RagStatus.EMBEDDER_UNAVAILABLE: "Embedding model không khả dụng.",
    RagStatus.INDEX_NOT_READY: "Vectorstore chưa được tạo — hãy chạy POST /rag/index.",
    RagStatus.RETRIEVAL_ERROR: "Lỗi khi truy xuất vectorstore.",
    RagStatus.NO_EVIDENCE: "Không tìm thấy tài liệu nào khớp truy vấn.",
    RagStatus.INDEX_INCOMPATIBLE: (
        "Index hiện có được build bằng cấu hình embedding khác — hãy chạy lại "
        "POST /rag/index."
    ),
    RagStatus.OK: "",
}


@router.post("/rag/search")
async def search_knowledge(query: str):
    """Tìm kiếm trong knowledge base.

    Trả về `status` để phân biệt rõ bốn tình huống từng bị gộp thành "rỗng":
    RAG tắt, index chưa sẵn sàng, không có bằng chứng khớp, và lỗi truy xuất.
    """
    result = await run_in_threadpool(rag_service.retrieve_detailed, query, 5)
    payload = {
        "status": result.status.value,
        "message": _RAG_STATUS_MESSAGES.get(result.status, ""),
        "detail": result.detail,
        "num_results": len(result.documents),
        "results": result.context,
        # Nguồn có cấu trúc: doc_id/chunk_id ổn định (gán nhãn eval được) kèm
        # đoạn bằng chứng, thay vì chỉ một đường dẫn tuyệt đối của máy build.
        "sources": [
            {
                "doc_id": doc.metadata.get("doc_id"),
                "chunk_id": doc.metadata.get("chunk_id"),
                "source": doc.metadata.get("source", "N/A"),
                "page": doc.metadata.get("page"),
                "section": doc.metadata.get("section") or None,
                "language": doc.metadata.get("language"),
                "content_hash": doc.metadata.get("content_hash"),
                "score": score,
                "evidence": evidence_snippet(doc.page_content, query),
            }
            for doc, score in result.documents
        ],
        "index_version": rag_service.active_version(),
    }
    if result.degraded:
        # Hệ thống đang hỏng, không phải "không có kết quả" -> đừng trả 200.
        return JSONResponse(status_code=503, content=payload)
    return payload


@router.get("/db/status")
async def db_status(db: AsyncSession = Depends(get_db)):
    """Kiểm tra kết nối MySQL khi USE_DATABASE=true."""
    await db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}


@router.get("/chat/history", response_model=list[ChatMessage])
async def get_chat_history(
    user: User = Depends(_get_current_user),
):
    """Lấy lịch sử chat của user."""
    try:
        settings = get_settings()
        db = None
        db_context = None
        if settings.use_database:
            from app.db.database import _get_engine_and_sessionmaker
            _, session_factory = _get_engine_and_sessionmaker()
            db_context = session_factory()
            db = await db_context.__aenter__()
        try:
            history = await chat_memory_service.get_history(user.id, db=db)
            return [ChatMessage(role=m["role"], content=m["content"]) for m in history]
        finally:
            if db_context:
                await db_context.__aexit__(None, None, None)
    except LLMNotConfiguredError:
        raise
    except Exception as e:
        logger.exception("Error in get_chat_history: {}", e)
        raise HTTPException(status_code=500, detail=_INTERNAL_ERROR)


@router.delete("/chat/history")
async def delete_chat_history(
    user: User = Depends(_get_current_user),
):
    """Xóa lịch sử chat của user."""
    try:
        settings = get_settings()
        db = None
        db_context = None
        if settings.use_database:
            from app.db.database import _get_engine_and_sessionmaker
            _, session_factory = _get_engine_and_sessionmaker()
            db_context = session_factory()
            db = await db_context.__aenter__()
        try:
            await chat_memory_service.clear_history(user.id, db=db)
            return {"status": "ok", "message": "Lịch sử chat đã được xóa."}
        finally:
            if db_context:
                await db_context.__aexit__(None, None, None)
    except LLMNotConfiguredError:
        raise
    except Exception as e:
        logger.exception("Error in delete_chat_history: {}", e)
        raise HTTPException(status_code=500, detail=_INTERNAL_ERROR)
