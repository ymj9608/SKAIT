from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .demo import build_demo_session
from .repository import SessionRepository
from .schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    LectureSession,
    SessionCreate,
    SessionUpdate,
    StatusUpdate,
    TranscriptCreate,
    TranscriptSegment,
    TranscriptUpdate,
)
from .services.stt import SpeechToText, build_stt
from .services.study import (
    StudyAssistant,
    build_recent_learning_context,
    build_study_assistant,
    merge_learning_items,
)


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.repository = SessionRepository(
        settings.database_file,
        legacy_json_file=settings.data_file,
    )
    app.state.stt = None
    app.state.stt_error = None
    app.state.assistant = None
    app.state.llm_error = None
    try:
        app.state.stt = build_stt(settings)
    except (RuntimeError, ImportError) as exc:
        app.state.stt_error = str(exc)
    try:
        app.state.assistant = build_study_assistant(settings)
    except (RuntimeError, ImportError) as exc:
        app.state.llm_error = str(exc)
    try:
        yield
    finally:
        app.state.repository.close()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Zoom·YouTube 수업 음성을 기록하고 요약·질의응답을 제공하는 로컬 학습 에이전트 API",
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


async def regenerate_material(session: LectureSession) -> None:
    """전체 노트를 갱신하면서 실시간으로 찾은 term/concept를 보존합니다."""
    previous_items = list(session.material.learning_items)
    refreshed = await assistant_or_503().summarize(session.segments)
    summarized_items = list(refreshed.learning_items)
    refreshed.learning_items = previous_items
    session.material = merge_learning_items(refreshed, summarized_items)


async def detect_latest_learning_items(session: LectureSession) -> None:
    """직전 최대 90초를 보조 문맥으로 사용해 현재 30초의 장애물만 탐지합니다."""
    previous_context, current_context = build_recent_learning_context(session.segments)
    if not current_context:
        return
    recent_titles = [item.title for item in session.material.learning_items[-20:]]
    detected = await assistant_or_503().detect_learning_items(
        previous_context,
        current_context,
        recent_titles,
    )
    if detected:
        session.material = merge_learning_items(session.material, detected)


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
        stt_error=app.state.stt_error if not stt_ready else None,
        llm_error=app.state.llm_error if not llm_ready else None,
    )


@app.get("/api/sessions", response_model=list[LectureSession])
async def list_sessions() -> list[LectureSession]:
    return repository().list()


@app.post("/api/sessions", response_model=LectureSession, status_code=201)
async def create_session(payload: SessionCreate) -> LectureSession:
    return repository().save(
        LectureSession(
            title=payload.title,
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
    session.title = payload.title
    return repository().save(session)


@app.patch("/api/sessions/{session_id}/status", response_model=LectureSession)
async def update_status(session_id: str, payload: StatusUpdate) -> LectureSession:
    session = get_session_or_404(session_id)
    session.status = payload.status
    if payload.duration_seconds is not None:
        session.duration_seconds = max(session.duration_seconds, payload.duration_seconds)
    if payload.status == "completed" and session.segments:
        await regenerate_material(session)
        await detect_latest_learning_items(session)
    return repository().save(session)


@app.post("/api/sessions/{session_id}/transcript", response_model=LectureSession)
async def append_transcript(session_id: str, payload: TranscriptCreate) -> LectureSession:
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
    session.duration_seconds = max(session.duration_seconds, start_seconds)
    # 직접 입력은 테스트·보정 흐름이므로 즉시 AI 노트를 갱신합니다.
    await regenerate_material(session)
    await detect_latest_learning_items(session)
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
    session = get_session_or_404(session_id)
    segment = next((item for item in session.segments if item.id == segment_id), None)
    if segment is None:
        raise HTTPException(status_code=404, detail="수업 내용을 찾을 수 없습니다.")
    segment.text = payload.text
    await regenerate_material(session)
    return repository().save(session)


@app.post("/api/sessions/{session_id}/audio", response_model=LectureSession)
async def transcribe_audio(
    session_id: str,
    audio: UploadFile = File(...),
    start_seconds: float = Form(default=0, ge=0),
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
        result = await stt.transcribe(raw, audio.filename or "lecture.webm")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"음성 인식에 실패했습니다: {exc}") from exc
    if not result.text:
        # YouTube 인트로 음악이나 짧은 무음은 정상적인 실시간 구간입니다.
        # 오류 알림을 띄우지 않고 수집 시간만 보존합니다.
        session.duration_seconds = max(session.duration_seconds, start_seconds)
        return repository().save(session)
    session.segments.append(
        TranscriptSegment(
            start_seconds=start_seconds,
            speaker="강사" if session.source_type == "youtube" else "교수님",
            text=result.text,
            confidence=result.confidence,
        )
    )
    session.duration_seconds = max(session.duration_seconds, start_seconds)
    # 전체 노트는 설정된 간격으로 생성하되, 그 사이에는 짧은 전문용어
    # 탐지 프롬프트만 실행해 30초 구간의 어려운 개념을 놓치지 않습니다.
    if (
        len(session.segments) == 1
        or len(session.segments) % settings.summary_interval_segments == 0
    ):
        await regenerate_material(session)
    await detect_latest_learning_items(session)
    return repository().save(session)


@app.post("/api/sessions/{session_id}/summary", response_model=LectureSession)
async def refresh_summary(session_id: str) -> LectureSession:
    session = get_session_or_404(session_id)
    await regenerate_material(session)
    await detect_latest_learning_items(session)
    return repository().save(session)


@app.post("/api/sessions/{session_id}/chat", response_model=ChatResponse)
async def chat(session_id: str, payload: ChatRequest) -> ChatResponse:
    session = get_session_or_404(session_id)
    return await assistant_or_503().answer(
        payload.message,
        session.segments,
        session.material,
        payload.history,
    )


@app.delete("/api/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str) -> Response:
    if not repository().delete(session_id):
        raise HTTPException(status_code=404, detail="학습 세션을 찾을 수 없습니다.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
