from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlparse
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TranscriptSegment(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    start_seconds: float = Field(default=0, ge=0)
    speaker: str = "교수님"
    text: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0, le=1)


class SourceReference(BaseModel):
    segment_id: str
    start_seconds: float
    speaker: str
    excerpt: str


class StudyMaterial(BaseModel):
    summary: str = "아직 정리할 수업 내용이 없습니다. 녹음을 시작하거나 텍스트를 추가해 주세요."
    key_points: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    review_questions: list[str] = Field(default_factory=list)


class LectureSession(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    title: str = "새 학습 세션"
    course_name: str = "SKALA Zoom 수업"
    source_type: Literal["zoom", "youtube", "demo"] = "zoom"
    source_url: str | None = Field(default=None, max_length=2_048)
    created_at: datetime = Field(default_factory=utc_now)
    status: Literal["ready", "recording", "completed"] = "ready"
    duration_seconds: float = Field(default=0, ge=0)
    segments: list[TranscriptSegment] = Field(default_factory=list)
    material: StudyMaterial = Field(default_factory=StudyMaterial)


class SessionCreate(BaseModel):
    title: str = Field(default="새 학습 세션", min_length=1, max_length=100)
    course_name: str = Field(default="SKALA Zoom 수업", min_length=1, max_length=100)
    source_type: Literal["zoom", "youtube"] = "zoom"
    source_url: str | None = Field(default=None, max_length=2_048)

    @model_validator(mode="after")
    def validate_source(self) -> "SessionCreate":
        if self.source_type != "youtube":
            self.source_url = None
            return self

        value = (self.source_url or "").strip()
        parsed = urlparse(value)
        allowed_hosts = {
            "youtube.com",
            "www.youtube.com",
            "m.youtube.com",
            "music.youtube.com",
            "youtu.be",
        }
        if parsed.scheme != "https" or (parsed.hostname or "").lower() not in allowed_hosts:
            raise ValueError("올바른 https:// YouTube 영상 주소를 입력해 주세요.")
        self.source_url = value
        return self


class TranscriptCreate(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    speaker: str = Field(default="교수님", max_length=30)
    start_seconds: float | None = Field(default=None, ge=0)


class StatusUpdate(BaseModel):
    status: Literal["ready", "recording", "completed"]
    duration_seconds: float | None = Field(default=None, ge=0)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2_000)


class ChatResponse(BaseModel):
    answer: str
    class_context: str | None = None
    supplementary_explanation: str | None = None
    knowledge_scope: Literal["class_only", "class_plus_general"] = "class_only"
    sources: list[SourceReference] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    stt_provider: str
    llm_provider: str
    stt_model: str | None = None
    llm_model: str | None = None
    stt_ready: bool
    llm_ready: bool
    stt_error: str | None = None
    llm_error: str | None = None
