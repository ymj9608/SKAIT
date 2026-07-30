import asyncio
import logging
import sqlite3
from contextlib import asynccontextmanager
from typing import Awaitable, TypeVar
from uuid import uuid4

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware

from .client_lifecycle import ClientConnectionTracker
from .config import get_settings
from .demo import build_demo_session
from .repository import SessionRepository, migrate_legacy_database
from .schemas import (
    ChatRequest,
    ChatResponse,
    ChatMessage,
    CategoryCreate,
    CategoryUpdate,
    ConversationMessage,
    EMPTY_SUMMARY_TEXT,
    HealthResponse,
    LectureSession,
    ReferenceDocument,
    SessionCreate,
    SessionUpdate,
    StatusUpdate,
    StudyCategory,
    StudyMaterial,
    SummaryBatchUpdate,
    SummaryCard,
    SummaryNote,
    SummaryNoteCreate,
    TranscriptBatchUpdate,
    TranscriptCreate,
    TranscriptSegment,
    TranscriptUpdate,
    utc_now,
)
from .services.pdf import extract_pdf_text
from .services.stt import SpeechToText, build_stt
from .services.study import (
    StudyAssistant,
    build_study_assistant,
    build_quiz_context,
    format_timestamp,
    merge_learning_items,
    quiz_question_count,
    remove_duplicate_topics,
    summary_card_text,
)


settings = get_settings()
logger = logging.getLogger(__name__)
MAX_REFERENCE_DOCUMENTS = 20
CLIENT_IDLE_SECONDS = 10
_SESSION_PIPELINE_LOCKS: dict[str, asyncio.Lock] = {}
AI_RESULT = TypeVar("AI_RESULT")


@asynccontextmanager
async def session_pipeline(session_id: str):
    """같은 수업의 전사·AI·참고 자료 변경은 순서대로 적용합니다."""
    lock = _SESSION_PIPELINE_LOCKS.setdefault(session_id, asyncio.Lock())
    async with lock:
        yield


async def tracked_ai_call(operation: Awaitable[AI_RESULT]) -> AI_RESULT:
    """브라우저 연결 종료 시 취소할 수 있도록 현재 AI 요청을 등록합니다."""
    task = asyncio.current_task()
    active_tasks: set[asyncio.Task] | None = getattr(
        app.state,
        "active_ai_tasks",
        None,
    )
    if task is not None and active_tasks is not None:
        active_tasks.add(task)
    try:
        return await operation
    finally:
        if task is not None and active_tasks is not None:
            active_tasks.discard(task)


async def cancel_active_ai_operations(app_instance: FastAPI) -> None:
    current_task = asyncio.current_task()
    active_tasks: set[asyncio.Task] = getattr(
        app_instance.state,
        "active_ai_tasks",
        set(),
    )
    tasks = [
        task
        for task in tuple(active_tasks)
        if task is not current_task and not task.done()
    ]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def release_idle_ai_resources(app_instance: FastAPI) -> None:
    """연결된 브라우저가 없을 때 AI 요청을 취소하고 Ollama 모델을 내립니다."""
    tracker: ClientConnectionTracker = app_instance.state.client_connections
    if tracker.has_connections:
        return
    await cancel_active_ai_operations(app_instance)
    if tracker.has_connections:
        return
    assistant: StudyAssistant | None = app_instance.state.assistant
    if assistant is not None:
        logger.info(
            "no SKAIT browser connection for %s seconds; unloading AI resources",
            CLIENT_IDLE_SECONDS,
        )
        await assistant.close()


async def monitor_client_connections(app_instance: FastAPI) -> None:
    tracker: ClientConnectionTracker = app_instance.state.client_connections
    while True:
        await asyncio.sleep(1)
        if tracker.claim_idle_cleanup():
            await release_idle_ai_resources(app_instance)


@asynccontextmanager
async def lifespan(app: FastAPI):
    migrate_legacy_database(settings.database_file)
    app.state.repository = SessionRepository(
        settings.database_file,
        legacy_json_file=settings.data_file,
    )
    app.state.stt = None
    app.state.stt_error = None
    app.state.assistant = None
    app.state.llm_error = None
    app.state.active_ai_tasks = set()
    app.state.client_connections = ClientConnectionTracker(CLIENT_IDLE_SECONDS)
    app.state.client_monitor_task = None
    try:
        app.state.stt = build_stt(settings)
    except (RuntimeError, ImportError) as exc:
        app.state.stt_error = str(exc)
    try:
        app.state.assistant = build_study_assistant(settings)
    except (RuntimeError, ImportError) as exc:
        app.state.llm_error = str(exc)
    app.state.client_monitor_task = asyncio.create_task(
        monitor_client_connections(app)
    )
    try:
        yield
    finally:
        monitor_task: asyncio.Task | None = app.state.client_monitor_task
        if monitor_task is not None:
            monitor_task.cancel()
            await asyncio.gather(monitor_task, return_exceptions=True)
        try:
            await cancel_active_ai_operations(app)
            assistant = app.state.assistant
            if assistant is not None:
                await assistant.close()
        finally:
            app.state.repository.close()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Zoom·YouTube 수업 음성을 기록하고 요약·질의응답을 제공하는 로컬 AI 학습 도우미 API",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def repository() -> SessionRepository:
    return app.state.repository


def get_session_or_404(session_id: str) -> LectureSession:
    session = repository().get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="학습 세션을 찾을 수 없습니다.")
    return session


def assistant_or_503() -> StudyAssistant:
    assistant = app.state.assistant
    if not assistant:
        raise HTTPException(
            status_code=503,
            detail=app.state.llm_error or "학습 모델을 사용할 수 없습니다.",
        )
    return assistant


def refresh_material_digest(session: LectureSession) -> None:
    """기존 챗봇·AI 노트 소비자를 위해 카드의 최신 핵심을 material에도 투영합니다."""
    topics = [
        topic
        for card in session.material.summary_cards[-3:]
        for topic in card.topics
    ]
    if not topics:
        session.material.summary = EMPTY_SUMMARY_TEXT
        session.material.key_points = []
        return
    session.material.summary = " ".join(topic.summary for topic in topics[-2:])
    session.material.key_points = [
        point
        for topic in topics
        for point in topic.key_points
    ][-5:]


async def regenerate_material(session: LectureSession) -> None:
    """이전 호출부와 호환되도록 전체 배치 요약·학습 항목을 다시 만듭니다."""
    await rebuild_study_material(session)


async def refine_transcript_segment(
    session: LectureSession,
    segment: TranscriptSegment,
) -> bool:
    context_start = max(0, segment.start_seconds - 90)
    previous_segments = [
        item
        for item in session.segments
        if item.id != segment.id
        and item.is_refined
        and context_start <= item.start_seconds < segment.start_seconds
    ]
    if not previous_segments:
        previous_segments = [
            item
            for item in session.segments
            if item.id != segment.id and item.is_refined
        ][-3:]
    previous_context = "\n".join(
        f"[{format_timestamp(item.start_seconds)}] {item.speaker}: {item.text}"
        for item in previous_segments[-12:]
    )
    cleaned = await tracked_ai_call(
        assistant_or_503().refine_transcript(
            previous_context,
            segment.text,
        )
    )
    if not cleaned:
        return False
    segment.text = cleaned
    segment.is_refined = True
    return True


async def detect_learning_items_window(
    session: LectureSession,
    window_start: float,
    window_end: float,
    segments: list[TranscriptSegment],
) -> None:
    if not segments:
        return
    context_start = max(0, window_start - 90)
    previous_segments = [
        segment
        for segment in session.segments
        if segment.is_refined
        and context_start <= segment.start_seconds < window_start
    ]
    previous_context = "\n".join(
        f"[{format_timestamp(segment.start_seconds)}] {segment.speaker}: {segment.text}"
        for segment in previous_segments
    )
    current_context = "\n".join(
        f"[{format_timestamp(segment.start_seconds)}] {segment.speaker}: {segment.text}"
        for segment in segments
    )
    recent_titles = [item.title for item in session.material.learning_items[-10:]]
    detected = await tracked_ai_call(
        assistant_or_503().detect_learning_items(
            previous_context,
            current_context,
            recent_titles,
        )
    )
    # 새 항목이 없어도 이전 버전에서 과도하게 쌓인 항목 수는 보수적인 한도로 줄입니다.
    session.material = merge_learning_items(session.material, detected)


async def process_learning_item_batches(
    session: LectureSession,
    through_seconds: float,
    *,
    include_partial: bool = False,
) -> None:
    """저장된 STT를 30초 창으로 묶어 용어·중요 개념을 빠르게 갱신합니다."""
    cursor = session.material.learning_items_processed_through_seconds
    through_seconds = max(cursor, through_seconds)
    batch_seconds = float(settings.learning_item_batch_seconds)

    while cursor + batch_seconds <= through_seconds + 0.001:
        window_end = cursor + batch_seconds
        window_segments = [
            segment
            for segment in session.segments
            if segment.is_refined and cursor <= segment.start_seconds < window_end
        ]
        await detect_learning_items_window(
            session,
            cursor,
            window_end,
            window_segments,
        )
        cursor = window_end
        session.material.learning_items_processed_through_seconds = cursor

    if include_partial and through_seconds > cursor + 0.001:
        window_segments = [
            segment
            for segment in session.segments
            if segment.is_refined and cursor <= segment.start_seconds <= through_seconds
        ]
        await detect_learning_items_window(
            session,
            cursor,
            through_seconds,
            window_segments,
        )
        cursor = through_seconds
        session.material.learning_items_processed_through_seconds = cursor


async def summarize_window(
    session: LectureSession,
    window_start: float,
    window_end: float,
    segments: list[TranscriptSegment],
) -> None:
    if not segments:
        return
    previous_cards = session.material.summary_cards
    previous_context_parts: list[str] = []
    if previous_cards:
        previous_context_parts.append(
            f"[직전 요약 카드]\n{summary_card_text(previous_cards[-1])[:1_200]}"
        )
    continuity_start = max(0, window_start - 60)
    continuity_segments = [
        segment
        for segment in session.segments
        if segment.is_refined
        and continuity_start <= segment.start_seconds < window_start
    ][-3:]
    if continuity_segments:
        previous_context_parts.append(
            "[직전 발화 맥락·대명사와 이어지는 설명 확인 전용]\n"
            + "\n".join(
                f"[{format_timestamp(segment.start_seconds)}] "
                f"{segment.speaker}: {segment.text}"
                for segment in continuity_segments
            )[:1_500]
        )
    previous_summary = "\n\n".join(previous_context_parts)
    recent_topics = [
        topic.title
        for card in previous_cards[-5:]
        for topic in card.topics
    ]
    if session.reference_text:
        result = await tracked_ai_call(
            assistant_or_503().summarize_batch(
                segments,
                previous_summary,
                recent_topics,
                session.reference_text,
            )
        )
    else:
        result = await tracked_ai_call(
            assistant_or_503().summarize_batch(
                segments,
                previous_summary,
                recent_topics,
            )
        )
    result = remove_duplicate_topics(result, previous_cards)
    if not result.has_meaningful_content or not result.topics:
        return

    session.material.summary_cards.append(
        SummaryCard(
            start_seconds=window_start,
            end_seconds=window_end,
            topics=result.topics,
            source_segment_ids=[segment.id for segment in segments],
        )
    )
    refresh_material_digest(session)


async def process_summary_batches(
    session: LectureSession,
    through_seconds: float,
    *,
    include_partial: bool = False,
    batch_seconds: int | float | None = None,
) -> None:
    """전사를 선택한 주기의 창으로 묶고, 처리 완료 지점을 의미 없는 창까지 기록합니다."""
    cursor = session.material.summary_processed_through_seconds
    through_seconds = max(cursor, through_seconds)
    batch_seconds = float(
        settings.summary_batch_seconds if batch_seconds is None else batch_seconds
    )

    while cursor + batch_seconds <= through_seconds + 0.001:
        window_end = cursor + batch_seconds
        window_segments = [
            segment
            for segment in session.segments
            if segment.is_refined and cursor <= segment.start_seconds < window_end
        ]
        await summarize_window(session, cursor, window_end, window_segments)
        cursor = window_end
        session.material.summary_processed_through_seconds = cursor

    if include_partial and through_seconds > cursor + 0.001:
        window_segments = [
            segment
            for segment in session.segments
            if segment.is_refined and cursor <= segment.start_seconds <= through_seconds
        ]
        await summarize_window(session, cursor, through_seconds, window_segments)
        cursor = through_seconds
        session.material.summary_processed_through_seconds = cursor


async def rebuild_study_material(session: LectureSession) -> None:
    """원문 보정 뒤 30초 학습 항목과 2분 요약 카드를 일관되게 다시 만듭니다."""
    personal_notes = [note.model_copy(deep=True) for note in session.material.summary_notes]
    quiz_questions = [
        question.model_copy(deep=True)
        for question in session.material.quiz_questions
    ]
    session.material = StudyMaterial(
        summary_notes=personal_notes,
        quiz_questions=quiz_questions,
        quiz_generated_at=session.material.quiz_generated_at,
    )
    await process_summary_batches(
        session,
        session.duration_seconds,
        include_partial=True,
    )
    await process_learning_item_batches(
        session,
        session.duration_seconds,
        include_partial=True,
    )


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": settings.app_name, "docs": "/docs", "health": "/api/health"}


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    stt = app.state.stt
    assistant = app.state.assistant
    stt_ready = bool(stt and await stt.is_ready())
    llm_ready = bool(assistant and await assistant.is_ready())
    return HealthResponse(
        version=settings.app_version,
        stt_provider=settings.stt_provider,
        llm_provider=settings.llm_provider,
        stt_model=getattr(stt, "model_name", None),
        llm_model=getattr(assistant, "model_name", None),
        stt_ready=stt_ready,
        llm_ready=llm_ready,
        learning_item_batch_seconds=settings.learning_item_batch_seconds,
        summary_batch_seconds=settings.summary_batch_seconds,
        stt_error=app.state.stt_error if not stt_ready else None,
        llm_error=app.state.llm_error if not llm_ready else None,
    )


@app.websocket("/api/client/connection")
async def client_connection(websocket: WebSocket) -> None:
    """열려 있는 각 SKAIT 탭의 연결을 서버 자원 수명과 연결합니다."""
    connection_id = uuid4().hex
    tracker: ClientConnectionTracker = app.state.client_connections
    await websocket.accept()
    tracker.connect(connection_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        tracker.disconnect(connection_id)


@app.get("/api/sessions", response_model=list[LectureSession])
async def list_sessions() -> list[LectureSession]:
    return repository().list()


@app.get("/api/categories", response_model=list[StudyCategory])
async def list_categories() -> list[StudyCategory]:
    return repository().list_categories()


@app.post("/api/categories", response_model=StudyCategory, status_code=201)
async def create_category(payload: CategoryCreate) -> StudyCategory:
    if payload.parent_id and not repository().get_category(payload.parent_id):
        raise HTTPException(status_code=404, detail="상위 카테고리를 찾을 수 없습니다.")
    try:
        return repository().create_category(
            StudyCategory(name=payload.name, parent_id=payload.parent_id)
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="같은 이름의 카테고리가 이미 있습니다.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.patch("/api/categories/{category_id}", response_model=StudyCategory)
async def update_category(category_id: str, payload: CategoryUpdate) -> StudyCategory:
    update_parent = "parent_id" in payload.model_fields_set
    if (
        update_parent
        and payload.parent_id
        and not repository().get_category(payload.parent_id)
    ):
        raise HTTPException(status_code=404, detail="상위 레포지토리를 찾을 수 없습니다.")
    try:
        category = repository().update_category(
            category_id,
            payload.name,
            parent_id=payload.parent_id,
            update_parent=update_parent,
            sort_order=payload.sort_order,
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="같은 이름의 카테고리가 이미 있습니다.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if category is None:
        raise HTTPException(status_code=404, detail="카테고리를 찾을 수 없습니다.")
    return category


@app.delete("/api/categories/{category_id}", status_code=204)
async def delete_category(category_id: str) -> Response:
    try:
        deleted = repository().delete_category(category_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="카테고리를 찾을 수 없습니다.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/sessions", response_model=LectureSession, status_code=201)
async def create_session(payload: SessionCreate) -> LectureSession:
    if payload.category_id and not repository().get_category(payload.category_id):
        raise HTTPException(status_code=404, detail="카테고리를 찾을 수 없습니다.")
    category_id = payload.category_id or repository().default_category().id
    return repository().save(
        LectureSession(
            title=payload.title,
            category_id=category_id,
            course_name=payload.course_name,
            source_type=payload.source_type,
            source_url=payload.source_url,
        )
    )


@app.post("/api/sessions/demo", response_model=LectureSession, status_code=201)
async def create_demo_session() -> LectureSession:
    return repository().save(build_demo_session())


@app.get("/api/sessions/{session_id}", response_model=LectureSession)
async def get_session(session_id: str) -> LectureSession:
    return get_session_or_404(session_id)


@app.patch("/api/sessions/{session_id}", response_model=LectureSession)
async def update_session(session_id: str, payload: SessionUpdate) -> LectureSession:
    session = get_session_or_404(session_id)
    if payload.title is not None:
        session.title = payload.title
        session.title_revision += 1
    if "category_id" in payload.model_fields_set:
        if payload.category_id and not repository().get_category(payload.category_id):
            raise HTTPException(status_code=404, detail="카테고리를 찾을 수 없습니다.")
        session.category_id = (
            payload.category_id or repository().default_category().id
        )
        session.category_revision += 1
        session.organization_revision += 1
    if "sort_order" in payload.model_fields_set:
        session.sort_order = payload.sort_order
        session.organization_revision += 1
    return repository().save(session)


@app.patch("/api/sessions/{session_id}/status", response_model=LectureSession)
async def update_status(session_id: str, payload: StatusUpdate) -> LectureSession:
    async with session_pipeline(session_id):
        session = get_session_or_404(session_id)
        session.status = payload.status
        if payload.duration_seconds is not None:
            session.duration_seconds = max(session.duration_seconds, payload.duration_seconds)
        if payload.status == "completed" and session.segments:
            await process_summary_batches(
                session,
                session.duration_seconds,
                include_partial=True,
                batch_seconds=payload.summary_batch_seconds,
            )
            await process_learning_item_batches(
                session,
                session.duration_seconds,
                include_partial=True,
            )
        return repository().save(session)


@app.post("/api/sessions/{session_id}/transcript", response_model=LectureSession)
async def append_transcript(session_id: str, payload: TranscriptCreate) -> LectureSession:
    async with session_pipeline(session_id):
        session = get_session_or_404(session_id)
        start_seconds = (
            payload.start_seconds
            if payload.start_seconds is not None
            else session.duration_seconds
        )
        session.segments.append(
            TranscriptSegment(
                start_seconds=start_seconds,
                speaker=payload.speaker,
                text=payload.text.strip(),
                confidence=1,
            )
        )
        # 원문을 먼저 영구 저장한 뒤 30초 탐지와 요약을 실행합니다.
        session.duration_seconds = max(session.duration_seconds, start_seconds + 1)
        repository().save(session)
        await process_summary_batches(
            session,
            session.duration_seconds,
            include_partial=True,
        )
        await process_learning_item_batches(
            session,
            session.duration_seconds,
            include_partial=True,
        )
        return repository().save(session)


@app.patch("/api/sessions/{session_id}/transcript", response_model=LectureSession)
async def update_transcripts(
    session_id: str,
    payload: TranscriptBatchUpdate,
) -> LectureSession:
    """수업 내용을 한 번에 저장하고, AI 노트 갱신은 별도 요청으로 처리합니다."""
    async with session_pipeline(session_id):
        session = get_session_or_404(session_id)
        segments_by_id = {segment.id: segment for segment in session.segments}
        missing_ids = [item.id for item in payload.updates if item.id not in segments_by_id]
        if missing_ids:
            raise HTTPException(status_code=404, detail="수정할 수업 내용을 찾을 수 없습니다.")

        for item in payload.updates:
            segments_by_id[item.id].text = item.text
            segments_by_id[item.id].is_refined = True
        return repository().save(session)


@app.patch(
    "/api/sessions/{session_id}/transcript/{segment_id}",
    response_model=LectureSession,
)
async def update_transcript(
    session_id: str,
    segment_id: str,
    payload: TranscriptUpdate,
) -> LectureSession:
    async with session_pipeline(session_id):
        session = get_session_or_404(session_id)
        segment = next((item for item in session.segments if item.id == segment_id), None)
        if segment is None:
            raise HTTPException(status_code=404, detail="수업 내용을 찾을 수 없습니다.")
        segment.text = payload.text
        segment.is_refined = True
        await rebuild_study_material(session)
        return repository().save(session)


async def _attach_reference_pdfs_locked(
    session_id: str,
    documents: list[UploadFile],
) -> LectureSession:
    session = get_session_or_404(session_id)
    if not documents:
        raise HTTPException(status_code=400, detail="업로드할 PDF 파일을 선택해 주세요.")
    if len(session.references) + len(documents) > MAX_REFERENCE_DOCUMENTS:
        raise HTTPException(
            status_code=400,
            detail=f"PDF 참고 자료는 수업당 최대 {MAX_REFERENCE_DOCUMENTS}개까지 연결할 수 있습니다.",
        )

    extracted: list[ReferenceDocument] = []
    for document in documents:
        filename = (document.filename or "lecture-reference.pdf").replace("\\", "/").rsplit("/", 1)[-1]
        if not filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=415, detail="PDF 파일만 업로드할 수 있습니다.")
        raw = await document.read()
        if not raw:
            raise HTTPException(status_code=400, detail=f"“{filename}” PDF 파일이 비어 있습니다.")
        try:
            reference_text = extract_pdf_text(raw)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"“{filename}”: {exc}") from exc
        extracted.append(
            ReferenceDocument(name=filename[:255], text=reference_text)
        )

    session.references.extend(extracted)
    session.sync_reference_fields()
    if session.segments:
        await regenerate_material(session)
    return repository().save(session)


async def attach_reference_pdfs(
    session_id: str,
    documents: list[UploadFile],
) -> LectureSession:
    async with session_pipeline(session_id):
        return await _attach_reference_pdfs_locked(session_id, documents)


@app.post("/api/sessions/{session_id}/references", response_model=LectureSession)
async def upload_reference_pdfs(
    session_id: str,
    documents: list[UploadFile] = File(...),
) -> LectureSession:
    return await attach_reference_pdfs(session_id, documents)


@app.post("/api/sessions/{session_id}/reference", response_model=LectureSession)
async def upload_reference_pdf(
    session_id: str,
    document: UploadFile = File(...),
) -> LectureSession:
    """기존 단일 PDF 클라이언트와의 호환을 유지합니다."""
    return await attach_reference_pdfs(session_id, [document])


@app.delete(
    "/api/sessions/{session_id}/references/{reference_id}",
    response_model=LectureSession,
)
async def delete_reference_document(
    session_id: str,
    reference_id: str,
) -> LectureSession:
    async with session_pipeline(session_id):
        session = get_session_or_404(session_id)
        remaining = [
            reference for reference in session.references if reference.id != reference_id
        ]
        if len(remaining) == len(session.references):
            raise HTTPException(status_code=404, detail="PDF 참고 자료를 찾을 수 없습니다.")
        session.references = remaining
        if not remaining:
            session.reference_name = None
            session.reference_text = None
        session.sync_reference_fields()
        return repository().save(session)


@app.delete("/api/sessions/{session_id}/reference", response_model=LectureSession)
async def delete_reference_pdf(session_id: str) -> LectureSession:
    """기존 단일 PDF 삭제 요청은 연결된 자료 전체를 제거합니다."""
    async with session_pipeline(session_id):
        session = get_session_or_404(session_id)
        session.references = []
        session.reference_name = None
        session.reference_text = None
        session.sync_reference_fields()
        return repository().save(session)


@app.post("/api/sessions/{session_id}/audio", response_model=LectureSession)
async def transcribe_audio(
    session_id: str,
    audio: UploadFile = File(...),
    start_seconds: float = Form(default=0, ge=0),
    end_seconds: float | None = Form(default=None, ge=0),
    summary_batch_seconds: int = Form(
        default=min(300, max(60, settings.summary_batch_seconds)),
        ge=60,
        le=300,
    ),
) -> LectureSession:
    async with session_pipeline(session_id):
        return await _transcribe_audio_locked(
            session_id,
            audio,
            start_seconds,
            end_seconds,
            summary_batch_seconds,
        )


async def _transcribe_audio_locked(
    session_id: str,
    audio: UploadFile,
    start_seconds: float,
    end_seconds: float | None,
    summary_batch_seconds: int,
) -> LectureSession:
    session = get_session_or_404(session_id)
    stt: SpeechToText | None = app.state.stt
    if not stt:
        raise HTTPException(
            status_code=503,
            detail=app.state.stt_error or "STT 모델을 사용할 수 없습니다.",
        )
    raw = await audio.read(settings.max_audio_mb * 1024 * 1024 + 1)
    if not raw:
        raise HTTPException(status_code=400, detail="오디오 파일이 비어 있습니다.")
    if len(raw) > settings.max_audio_mb * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"오디오는 {settings.max_audio_mb}MB 이하의 구간으로 전송해 주세요.",
        )
    try:
        result = await tracked_ai_call(
            stt.transcribe(raw, audio.filename or "lecture.webm")
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"음성 인식에 실패했습니다: {exc}") from exc
    chunk_end_seconds = max(start_seconds, end_seconds or start_seconds)
    if not result.text:
        # YouTube 인트로 음악이나 짧은 무음은 정상적인 실시간 구간입니다.
        # 오류 알림을 띄우지 않고 수집 시간만 보존합니다.
        session.duration_seconds = max(session.duration_seconds, chunk_end_seconds)
        repository().save(session)
        await process_summary_batches(
            session,
            chunk_end_seconds,
            batch_seconds=summary_batch_seconds,
        )
        await process_learning_item_batches(session, chunk_end_seconds)
        return repository().save(session)
    corrected_text = result.text
    if session.reference_text:
        recent_context = "\n".join(
            item.text for item in session.segments[-3:] if item.is_refined
        )
        corrected_text = await tracked_ai_call(
            assistant_or_503().correct_transcript(
                result.text,
                session.reference_text,
                recent_context,
            )
        )
    segment = TranscriptSegment(
        start_seconds=start_seconds,
        speaker="강사" if session.source_type == "youtube" else "교수님",
        text=corrected_text,
        confidence=result.confidence,
        raw_text=result.text,
        is_refined=False,
    )
    session.segments.append(segment)
    session.duration_seconds = max(session.duration_seconds, chunk_end_seconds)
    # 원시 STT를 먼저 내부 저장한 뒤, 정제에 성공한 텍스트만 후속 단계에서 사용합니다.
    repository().save(session)
    if not await refine_transcript_segment(session, segment):
        return repository().save(session)
    repository().save(session)
    # 화면용 요약은 사용자 선택 주기, 용어·개념은 30초 창에서 생성합니다.
    await process_summary_batches(
        session,
        chunk_end_seconds,
        batch_seconds=summary_batch_seconds,
    )
    await process_learning_item_batches(session, chunk_end_seconds)
    return repository().save(session)


@app.post("/api/sessions/{session_id}/summary", response_model=LectureSession)
async def refresh_summary(session_id: str) -> LectureSession:
    async with session_pipeline(session_id):
        session = get_session_or_404(session_id)
        await rebuild_study_material(session)
        return repository().save(session)


@app.patch("/api/sessions/{session_id}/summary", response_model=LectureSession)
async def update_summaries(
    session_id: str,
    payload: SummaryBatchUpdate,
) -> LectureSession:
    async with session_pipeline(session_id):
        return await _update_summaries_locked(session_id, payload)


async def _update_summaries_locked(
    session_id: str,
    payload: SummaryBatchUpdate,
) -> LectureSession:
    """AI 요약 카드와 사용자가 추가한 요약을 재생성 없이 일괄 수정합니다."""
    session = get_session_or_404(session_id)
    cards_by_id = {card.id: card for card in session.material.summary_cards}
    notes_by_id = {note.id: note for note in session.material.summary_notes}
    requested_card_ids = [item.id for item in payload.cards] + payload.deleted_card_ids
    requested_note_ids = [item.id for item in payload.notes] + payload.deleted_note_ids
    missing_card_ids = [item_id for item_id in requested_card_ids if item_id not in cards_by_id]
    missing_note_ids = [item_id for item_id in requested_note_ids if item_id not in notes_by_id]
    if missing_card_ids or missing_note_ids:
        raise HTTPException(status_code=404, detail="수정할 요약 내용을 찾을 수 없습니다.")

    for item in payload.cards:
        cards_by_id[item.id].topics = [topic.model_copy(deep=True) for topic in item.topics]
    for item in payload.notes:
        notes_by_id[item.id].text = item.text

    deleted_card_ids = set(payload.deleted_card_ids)
    deleted_note_ids = set(payload.deleted_note_ids)
    session.material.summary_cards = [
        card
        for card in session.material.summary_cards
        if card.id not in deleted_card_ids
    ]
    session.material.summary_notes = [
        note
        for note in session.material.summary_notes
        if note.id not in deleted_note_ids
    ]
    if payload.notes or payload.deleted_note_ids:
        session.summary_notes_revision += 1

    refresh_material_digest(session)
    return repository().save(session)


@app.post("/api/sessions/{session_id}/summary-notes", response_model=LectureSession)
async def add_summary_note(
    session_id: str,
    payload: SummaryNoteCreate,
) -> LectureSession:
    session = get_session_or_404(session_id)
    session.material.summary_notes.append(SummaryNote(text=payload.text))
    session.summary_notes_revision += 1
    return repository().save(session)


@app.post("/api/sessions/{session_id}/quiz", response_model=LectureSession)
async def generate_quiz(session_id: str) -> LectureSession:
    session = get_session_or_404(session_id)
    summary_context = build_quiz_context(
        session.material,
        randomize_sections=True,
    )
    if not summary_context:
        raise HTTPException(
            status_code=409,
            detail="수업 내용이 없으므로 퀴즈를 생성할 수 없습니다.",
        )
    try:
        questions = await tracked_ai_call(
            assistant_or_503().generate_quiz(
                summary_context,
                quiz_question_count(summary_context),
            )
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    # 생성 중 녹음·요약·대화가 갱신될 수 있으므로 최신 세션에 퀴즈만 반영합니다.
    latest_session = get_session_or_404(session_id)
    latest_session.material.quiz_questions = questions
    latest_session.material.quiz_generated_at = utc_now()
    return repository().save(latest_session)


@app.post("/api/sessions/{session_id}/chat", response_model=ChatResponse)
async def chat(session_id: str, payload: ChatRequest) -> ChatResponse:
    session = get_session_or_404(session_id)
    clean_segments = [segment for segment in session.segments if segment.is_refined]
    stored_history = [
        ChatMessage(
            role=message.role,
            content="\n".join(
                part
                for part in (
                    message.text,
                    message.class_context,
                    message.supplementary_explanation,
                )
                if part
            )[:4_000],
        )
        for message in session.chat_messages[-12:]
    ]
    result = await tracked_ai_call(
        assistant_or_503().answer(
            payload.message,
            clean_segments,
            session.material,
            payload.history or stored_history,
        )
    )
    repository().append_chat_messages(
        session_id,
        [
            ConversationMessage(role="user", text=payload.message),
            ConversationMessage(
                role="assistant",
                text=result.answer,
                class_context=result.class_context,
                supplementary_explanation=result.supplementary_explanation,
                knowledge_scope=result.knowledge_scope,
                sources=result.sources,
            ),
        ],
    )
    return result


@app.delete("/api/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str) -> Response:
    async with session_pipeline(session_id):
        if not repository().delete(session_id):
            raise HTTPException(status_code=404, detail="학습 세션을 찾을 수 없습니다.")
        return Response(status_code=status.HTTP_204_NO_CONTENT)
