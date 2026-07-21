from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlparse
from uuid import uuid4

from pydantic import BaseModel, Field, field_serializer, model_validator


EMPTY_SUMMARY_TEXT = "아직 정리할 수업 내용이 없습니다. 녹음을 시작하거나 텍스트를 추가해 주세요."


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TranscriptSegment(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    start_seconds: float = Field(default=0, ge=0)
    speaker: str = "교수님"
    text: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    # 원시 STT는 내부 감사·재처리용으로만 보관하고 API 응답에는 노출하지 않습니다.
    raw_text: str | None = Field(default=None, exclude=True)
    is_refined: bool = Field(default=True, exclude=True)


class SourceReference(BaseModel):
    segment_id: str
    start_seconds: float
    speaker: str
    excerpt: str


class LearningItem(BaseModel):
    type: Literal["term", "concept"]
    title: str = Field(min_length=1, max_length=180)
    explanation: str = Field(min_length=1, max_length=500)


class SummaryTopic(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=800)
    key_points: list[str] = Field(default_factory=list, max_length=5)


class BatchSummaryResult(BaseModel):
    """LLM의 2분 배치 응답. 의미 없는 구간은 topics가 비어 있어야 합니다."""

    has_meaningful_content: bool = False
    topics: list[SummaryTopic] = Field(default_factory=list, max_length=2)


class QuizQuestion(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    question: str = Field(min_length=1, max_length=500)
    options: list[str] = Field(min_length=4, max_length=4)
    correct_option_index: int = Field(ge=0, le=3)
    explanation: str = Field(min_length=1, max_length=1_000)

    @model_validator(mode="after")
    def normalize_question(self) -> "QuizQuestion":
        self.question = self.question.strip()
        self.options = [option.strip() for option in self.options]
        self.explanation = self.explanation.strip()
        normalized_options = {
            "".join(option.split()).casefold()
            for option in self.options
            if option
        }
        if (
            not self.question
            or not self.explanation
            or any(not option for option in self.options)
            or len(normalized_options) != 4
        ):
            raise ValueError("퀴즈 문항과 서로 다른 네 개의 보기를 입력해 주세요.")
        return self


class SummaryCard(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    start_seconds: float = Field(default=0, ge=0)
    end_seconds: float = Field(default=0, ge=0)
    topics: list[SummaryTopic] = Field(min_length=1, max_length=2)
    source_segment_ids: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_time_range(self) -> "SummaryCard":
        if self.end_seconds < self.start_seconds:
            raise ValueError("요약 종료 시각은 시작 시각보다 빠를 수 없습니다.")
        return self


class SummaryNote(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    text: str = Field(min_length=1, max_length=20_000)
    created_at: datetime = Field(default_factory=utc_now)


class ConversationMessage(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=20_000)
    class_context: str | None = Field(default=None, max_length=20_000)
    supplementary_explanation: str | None = Field(default=None, max_length=20_000)
    knowledge_scope: Literal["class_only", "class_plus_general"] | None = None
    sources: list[SourceReference] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class SummaryNoteCreate(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)

    @model_validator(mode="after")
    def normalize_text(self) -> "SummaryNoteCreate":
        self.text = self.text.strip()
        if not self.text:
            raise ValueError("필기 내용을 입력해 주세요.")
        return self


class SummaryCardUpdate(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    topics: list[SummaryTopic] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def normalize_topics(self) -> "SummaryCardUpdate":
        for topic in self.topics:
            topic.title = topic.title.strip()
            topic.summary = topic.summary.strip()
            topic.key_points = [
                point.strip()
                for point in topic.key_points
                if point.strip()
            ]
            if not topic.title or not topic.summary:
                raise ValueError("요약 제목과 내용을 입력해 주세요.")
        return self


class SummaryNoteUpdate(SummaryNoteCreate):
    id: str = Field(min_length=1, max_length=64)


class SummaryBatchUpdate(BaseModel):
    cards: list[SummaryCardUpdate] = Field(default_factory=list, max_length=500)
    notes: list[SummaryNoteUpdate] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def validate_updates(self) -> "SummaryBatchUpdate":
        if not self.cards and not self.notes:
            raise ValueError("수정할 요약 내용을 입력해 주세요.")
        card_ids = [item.id for item in self.cards]
        note_ids = [item.id for item in self.notes]
        if len(card_ids) != len(set(card_ids)) or len(note_ids) != len(set(note_ids)):
            raise ValueError("같은 요약을 중복해서 수정할 수 없습니다.")
        return self


class StudyMaterial(BaseModel):
    summary: str = EMPTY_SUMMARY_TEXT
    key_points: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    keyword_explanations: dict[str, str] = Field(default_factory=dict)
    learning_items: list[LearningItem] = Field(default_factory=list)
    review_questions: list[str] = Field(default_factory=list)
    summary_cards: list[SummaryCard] = Field(default_factory=list)
    summary_notes: list[SummaryNote] = Field(default_factory=list)
    quiz_questions: list[QuizQuestion] = Field(default_factory=list, max_length=10)
    quiz_generated_at: datetime | None = None
    transcript_refinement_version: int = Field(default=1, ge=1)
    learning_items_processed_through_seconds: float = Field(default=0, ge=0)
    summary_processed_through_seconds: float = Field(default=0, ge=0)


class LectureSession(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    title: str = "새 수업"
    course_name: str = "SKALA Zoom 수업"
    source_type: Literal["zoom", "youtube", "demo"] = "zoom"
    source_url: str | None = Field(default=None, max_length=2_048)
    created_at: datetime = Field(default_factory=utc_now)
    status: Literal["ready", "recording", "completed"] = "ready"
    duration_seconds: float = Field(default=0, ge=0)
    reference_name: str | None = Field(default=None, max_length=255)
    reference_text: str | None = Field(default=None, exclude=True)
    segments: list[TranscriptSegment] = Field(default_factory=list)
    material: StudyMaterial = Field(default_factory=StudyMaterial)
    chat_messages: list[ConversationMessage] = Field(default_factory=list)

    @field_serializer("segments")
    def serialize_refined_segments(
        self,
        segments: list[TranscriptSegment],
    ) -> list[dict]:
        """API와 JSON에는 Qwen 정제를 통과한 전사만 노출합니다."""
        return [
            segment.model_dump(mode="json")
            for segment in segments
            if segment.is_refined
        ]

    @model_validator(mode="after")
    def migrate_legacy_summary_to_card(self) -> "LectureSession":
        """0.2 이전에 저장한 단일 AI 요약도 원문 대신 카드로 안전하게 표시합니다."""
        if (
            self.segments
            and not self.material.summary_cards
            and self.material.summary.strip()
            and self.material.summary != EMPTY_SUMMARY_TEXT
        ):
            end_seconds = max(
                self.duration_seconds,
                max(segment.start_seconds for segment in self.segments),
            )
            self.material.summary_cards = [
                SummaryCard(
                    start_seconds=0,
                    end_seconds=end_seconds,
                    topics=[
                        SummaryTopic(
                            title="이전 수업 요약",
                            summary=self.material.summary,
                            key_points=self.material.key_points[:5],
                        )
                    ],
                    source_segment_ids=[segment.id for segment in self.segments],
                )
            ]
            self.material.learning_items_processed_through_seconds = end_seconds
            self.material.summary_processed_through_seconds = end_seconds
        return self


class SessionCreate(BaseModel):
    title: str = Field(default="새 수업", min_length=1, max_length=100)
    course_name: str = Field(default="SKALA Zoom 수업", min_length=1, max_length=100)
    source_type: Literal["zoom", "youtube"] = "zoom"
    source_url: str | None = Field(default=None, max_length=2_048)

    @model_validator(mode="after")
    def validate_source(self) -> "SessionCreate":
        if self.source_type != "youtube":
            self.source_url = None
            return self

        value = (self.source_url or "").strip()
        if not value:
            self.source_url = None
            return self
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


class SessionUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def normalize_title(self) -> "SessionUpdate":
        self.title = self.title.strip()
        if not self.title:
            raise ValueError("수업 제목을 입력해 주세요.")
        return self


class TranscriptCreate(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    speaker: str = Field(default="교수님", max_length=30)
    start_seconds: float | None = Field(default=None, ge=0)


class TranscriptUpdate(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)

    @model_validator(mode="after")
    def normalize_text(self) -> "TranscriptUpdate":
        self.text = self.text.strip()
        if not self.text:
            raise ValueError("수업 내용을 입력해 주세요.")
        return self


class TranscriptBatchItem(TranscriptUpdate):
    id: str = Field(min_length=1, max_length=64)


class TranscriptBatchUpdate(BaseModel):
    updates: list[TranscriptBatchItem] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "TranscriptBatchUpdate":
        ids = [item.id for item in self.updates]
        if len(ids) != len(set(ids)):
            raise ValueError("같은 수업 내용을 중복해서 수정할 수 없습니다.")
        return self


class StatusUpdate(BaseModel):
    status: Literal["ready", "recording", "completed"]
    duration_seconds: float | None = Field(default=None, ge=0)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4_000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2_000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=12)


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
    learning_item_batch_seconds: int = 30
    summary_batch_seconds: int = 120
    stt_error: str | None = None
    llm_error: str | None = None
