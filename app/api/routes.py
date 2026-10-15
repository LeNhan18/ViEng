import asyncio
import json
import re
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import APIRouter, Body, Depends, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
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
from app.services.rag_service import rag_service
from app.services.jev_service import jev_service
from app.services.cache_service import cache_service, make_key
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
    """Chuyển text tiếng Anh thành audio (phát âm) — dùng Edge TTS miễn phí. Có cache."""
    try:
        settings = get_settings()
        clean = " ".join(text.split())
        key = make_key("tts", clean, settings.tts_voice)
        audio = await cache_service.get_bytes("tts", key)
        cached = audio is not None
        if not cached:
            import edge_tts

            communicate = edge_tts.Communicate(clean, settings.tts_voice)
            buf = bytearray()
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio":
                    buf.extend(chunk["data"])
            audio = bytes(buf)
            if audio:
                await cache_service.set_bytes(key, audio, settings.tts_cache_ttl_s)
        return Response(
            content=audio,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "inline; filename=speech.mp3",
                "Cache-Control": "public, max-age=86400",
                "X-Cache": "HIT" if cached else "MISS",
            },
        )
    except LLMNotConfiguredError:
        raise
    except Exception as e:
        logger.exception("TTS error: {}", e)
        raise HTTPException(status_code=500, detail="Không thể tạo audio. Vui lòng thử lại.")


@router.post("/translate", response_model=TranslateResponse)
async def translate_text(request: TranslateRequest):
    """Dịch thuật EN<->VI bằng AI, kết hợp RAG để tra cứu ngữ pháp/từ vựng liên quan. Có cache."""
    try:
        settings = get_settings()
        key = make_key(
            "translate", request.text.strip(), request.direction.value, request.level.value,
            request.use_rag, llm_service.model,
        )
        cached = await cache_service.get_json("translate", key)
        if cached is not None:
            rag_context = cached.get("rag_context", "")
            result = cached["result"]
        else:
            rag_context = ""
            if request.use_rag:
                query = request.text[:200]
                if request.direction.value == "en_to_vi":
                    query = f"grammar vocabulary {query}"
                rag_context = await run_in_threadpool(rag_service.retrieve, query, 3)

            result = await llm_service.translate(
                text=request.text,
                direction=request.direction.value,
                level=request.level.value,
                rag_context=rag_context,
                llm_provider=request.llm_provider,
            )
            # Chỉ cache bản dịch đầy đủ (không cache bản fallback thiếu từ vựng/ngữ pháp).
            if result.get("translated") and (result.get("vocabulary") or result.get("grammar_notes")):
                await cache_service.set_json(
                    key, {"result": result, "rag_context": (rag_context or "")[:500]},
                    settings.translate_cache_ttl_s,
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


@asynccontextmanager
async def _memory_session():
    """Session DB cho chat memory (None khi USE_DATABASE=false)."""
    if not get_settings().use_database:
        yield None
        return
    from app.db.database import _get_engine_and_sessionmaker

    _, session_factory = _get_engine_and_sessionmaker()
    async with session_factory() as session:
        yield session


def _extract_sources(rag_context: str) -> list[str]:
    sources: list[str] = []
    for m in re.finditer(r"\[Nguồn: ([^\]]+)\]", rag_context or ""):
        p = m.group(1).strip()
        name = Path(p).name if "/" in p or "\\" in p else p
        if name and name not in sources:
            sources.append(name)
    return sources[:5]


async def _rag_for_chat(message: str) -> str:
    """Jev quyết định có cần tra RAG không; chạy song song với RAG để không cộng dồn độ trễ."""
    rag_task = asyncio.ensure_future(run_in_threadpool(rag_service.retrieve_mmr, message, 4, 10))
    try:
        need = await jev_service.needs_rag(message)
    except Exception:  # noqa: BLE001 - jev đã fail-open, đây là phòng hờ
        need = True
    if not need:
        rag_task.cancel()
        return ""
    try:
        return await rag_task or ""
    except Exception as e:  # noqa: BLE001 - RAG lỗi không chặn chat
        logger.warning("RAG lỗi, bỏ qua context: {}", e)
        return ""


async def _prepare_chat(request: ChatRequest, user: User | None, db) -> tuple[list[dict], str, list[str]]:
    history: list[dict] = []
    if user:
        history = await chat_memory_service.get_history(
            user.id, db=db, limit=llm_service.CHAT_HISTORY_WINDOW
        )
    if not history:
        history = [{"role": h.role, "content": h.content} for h in request.history]
    rag_context = await _rag_for_chat(request.message)
    return history, rag_context, _extract_sources(rag_context)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    user: User | None = Depends(_get_current_user_optional)
):
    """Chatbot RAG + LLM: trả lời câu hỏi ngữ pháp/từ vựng TOEIC/IELTS dựa trên knowledge base."""
    try:
        async with _memory_session() as db:
            history, rag_context, sources = await _prepare_chat(request, user, db)
            reply = await llm_service.chat(
                message=request.message,
                history=history,
                rag_context=rag_context,
                llm_provider=request.llm_provider,
            )
            # Chỉ lưu khi LLM trả lời thành công: không để lại câu hỏi "mồ côi" trong lịch sử.
            if user:
                await chat_memory_service.save_turn(user.id, request.message, reply, sources, db=db)
            return ChatResponse(message=reply, sources=sources)
    except LLMNotConfiguredError:
        raise
    except Exception as e:
        logger.exception("Error in chat: {}", e)
        raise HTTPException(status_code=500, detail=_INTERNAL_ERROR)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    user: User | None = Depends(_get_current_user_optional),
):
    """Như /chat nhưng trả lời dạng Server-Sent Events.

    Sự kiện: `meta` {sources} -> nhiều `delta` {text} -> `done` {message, sources} | `error` {detail}.
    """
    llm_service.ensure_configured()  # thiếu key -> 503 trước khi mở stream

    async def events():
        try:
            async with _memory_session() as db:
                history, rag_context, sources = await _prepare_chat(request, user, db)
                yield _sse("meta", {"sources": sources})
                parts: list[str] = []
                async for delta in llm_service.chat_stream(
                    message=request.message,
                    history=history,
                    rag_context=rag_context,
                    llm_provider=request.llm_provider,
                ):
                    parts.append(delta)
                    yield _sse("delta", {"text": delta})
                reply = "".join(parts)
                if user and reply:
                    await chat_memory_service.save_turn(user.id, request.message, reply, sources, db=db)
                yield _sse("done", {"message": reply, "sources": sources})
        except Exception as e:  # noqa: BLE001 - báo lỗi trong stream, không lộ chi tiết
            logger.exception("Error in chat_stream: {}", e)
            yield _sse("error", {"detail": _INTERNAL_ERROR})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
        rag_context = await run_in_threadpool(rag_service.retrieve_mmr, user_question, 4, 10)
        sources = _extract_sources(rag_context)

        reply = await llm_service.chat(
            message=composed_message,
            history=[],
            rag_context=rag_context,
            llm_provider=llm_provider,
        )

        # Lưu tin nhắn và phản hồi vào memory nếu user đã đăng nhập
        if user:
            async with _memory_session() as db:
                await chat_memory_service.save_turn(
                    user.id, message.strip() or "(đã gửi file)", reply, sources, db=db
                )

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


_index_state: dict = {"status": "idle", "chunks": None, "started_at": None, "finished_at": None, "error": None}
_index_lock = asyncio.Lock()


def _require_admin(x_admin_token: str | None) -> None:
    settings = get_settings()
    if settings.admin_token:
        if x_admin_token != settings.admin_token:
            raise HTTPException(status_code=403, detail="Admin token không hợp lệ.")
    elif settings.app_env.lower() == "production":
        raise HTTPException(status_code=403, detail="Cần cấu hình ADMIN_TOKEN để index trên production.")


async def _run_index() -> None:
    import time

    _index_state.update(status="running", chunks=None, error=None, started_at=time.time(), finished_at=None)
    try:
        count = await run_in_threadpool(rag_service.index_knowledge_base)
        _index_state.update(status="done", chunks=count)
    except Exception as e:  # noqa: BLE001
        logger.exception("Index knowledge base lỗi: {}", e)
        _index_state.update(status="error", error=type(e).__name__)
    finally:
        _index_state["finished_at"] = time.time()


@router.post("/rag/index", status_code=202)
async def index_knowledge_base(x_admin_token: str | None = Header(None)):
    """Index lại knowledge base ở chế độ nền (không chặn server). Xem tiến độ: GET /rag/index/status."""
    _require_admin(x_admin_token)
    async with _index_lock:
        if _index_state["status"] == "running":
            raise HTTPException(status_code=409, detail="Đang index, vui lòng chờ.")
        _index_state["status"] = "running"
        asyncio.create_task(_run_index())
    return {"status": "started", "message": "Đang index knowledge base ở chế độ nền."}


@router.get("/rag/index/status")
async def index_status():
    return dict(_index_state)


@router.get("/rag/list")
async def list_vectorstore(limit: int = Query(20, ge=1, le=200), offset: int = Query(0, ge=0)):
    """Liệt kê các chunks trong vectorstore (phân trang ở phía Chroma, không tải toàn bộ)."""
    try:
        vs = await run_in_threadpool(rag_service._get_vectorstore)
        if vs is None:
            return {"chunks": [], "total": 0, "message": "Vectorstore chưa được tạo."}
        try:
            collection = vs._collection
            total = collection.count()
            data = collection.get(include=["documents", "metadatas"], limit=limit, offset=offset)
        except Exception as inner:
            logger.warning("Không đọc được collection nội bộ Chroma: {}", inner)
            return {
                "chunks": [],
                "total": 0,
                "message": "Không liệt kê được vectorstore (phiên bản Chroma hoặc lỗi truy cập).",
            }
        docs = data.get("documents") or []
        metas = data.get("metadatas") or [{}] * len(docs)
        chunks = []
        for i, (d, m) in enumerate(zip(docs, metas)):
            src = (m or {}).get("source") or "N/A"
            if isinstance(src, str):
                src = src.replace("\\", "/").split("/")[-1]
            chunks.append({
                "index": offset + i + 1,
                "source": src,
                "content": d[:500] + "..." if len(d) > 500 else d,
                "length": len(d),
            })
        return {"chunks": chunks, "total": total, "limit": limit, "offset": offset}
    except Exception as e:
        logger.exception("Error listing vectorstore: {}", e)
        raise HTTPException(status_code=500, detail=_INTERNAL_ERROR)


@router.post("/rag/search")
async def search_knowledge(query: str):
    """Tìm kiếm trong knowledge base."""
    context = await run_in_threadpool(rag_service.retrieve, query)
    if not context:
        return {"results": [], "message": "Không tìm thấy kết quả hoặc vectorstore chưa được tạo."}
    return {"results": context}


@router.get("/db/status")
async def db_status(db: AsyncSession = Depends(get_db)):
    """Kiểm tra kết nối MySQL khi USE_DATABASE=true."""
    await db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}


@router.get("/chat/history", response_model=list[ChatMessage])
async def get_chat_history(
    user: User = Depends(_get_current_user),
):
    """Lấy lịch sử chat của user (tối đa 100 tin gần nhất)."""
    try:
        async with _memory_session() as db:
            history = await chat_memory_service.get_history(user.id, db=db)
        return [ChatMessage(role=m["role"], content=m["content"]) for m in history]
    except Exception as e:
        logger.exception("Error in get_chat_history: {}", e)
        raise HTTPException(status_code=500, detail=_INTERNAL_ERROR)


@router.delete("/chat/history")
async def delete_chat_history(
    user: User = Depends(_get_current_user),
):
    """Xóa lịch sử chat của user."""
    try:
        async with _memory_session() as db:
            await chat_memory_service.clear_history(user.id, db=db)
        return {"status": "ok", "message": "Lịch sử chat đã được xóa."}
    except Exception as e:
        logger.exception("Error in delete_chat_history: {}", e)
        raise HTTPException(status_code=500, detail=_INTERNAL_ERROR)
