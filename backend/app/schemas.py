import re
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlparse
from uuid import uuid4

from pydantic import BaseModel, Field, field_serializer, model_validator


EMPTY_SUMMARY_TEXT = "아직 정리할 수업 내용이 없습니다. 녹음을 시작하거나 텍스트를 추가해 주세요."
KOREAN_TEXT_PATTERN = re.compile(r"[가-힣]")
LATIN_TEXT_PATTERN = re.compile(r"[A-Za-z]")
PARENTHESIZED_TERM_PATTERN = re.compile(
    r"^\s*([^()]*)\(\s*([^()]*)\s*\)\s*$"
)


def canonicalize_term_title(title: str) -> str:
    """한글 음역과 병기된 영어 기술 용어는 영어 원어만 유지합니다."""
    normalized = title.strip()
    match = PARENTHESIZED_TERM_PATTERN.fullmatch(normalized)
    if not match:
        return normalized

    outer, parenthesized = (part.strip() for part in match.groups())
    if (
        KOREAN_TEXT_PATTERN.search(outer)
        and LATIN_TEXT_PATTERN.search(parenthesized)
        and not KOREAN_TEXT_PATTERN.search(parenthesized)
    ):
        return parenthesized
    return normalized


HONORIFIC_ENDING_REPLACEMENTS = (
    ("아니다", "아닙니다"),
    ("않는다", "않습니다"),
    ("된다", "됩니다"),
    ("한다", "합니다"),
    ("이다", "입니다"),
    ("있다", "있습니다"),
    ("없다", "없습니다"),
    ("하다", "합니다"),
    ("어렵다", "어렵습니다"),
    ("쉽다", "쉽습니다"),
    ("같다", "같습니다"),
    ("높다", "높습니다"),
    ("낮다", "낮습니다"),
    ("좋다", "좋습니다"),
    ("낸다", "냅니다"),
    ("진다", "집니다"),
    ("든다", "듭니다"),
    ("는다", "습니다"),
    ("본다", "봅니다"),
    ("준다", "줍니다"),
    ("둔다", "둡니다"),
    ("쓴다", "씁니다"),
    ("셨어요", "셨습니다"),
    ("됐어요", "됐습니다"),
    ("했어요", "했습니다"),
    ("였어요", "였습니다"),
    ("았어요", "았습니다"),
    ("었어요", "었습니다"),
    ("하세요", "합니다"),
    ("돼요", "됩니다"),
    ("해요", "합니다"),
    ("이에요", "입니다"),
    ("예요", "입니다"),
    ("있어요", "있습니다"),
    ("없어요", "없습니다"),
)


def normalize_honorific_prose(text: str) -> str:
    """AI 학습 노트의 문장 종결을 보수적으로 하십시오체로 통일합니다."""
    normalized = text.strip()
    for plain, honorific in HONORIFIC_ENDING_REPLACEMENTS:
        normalized = re.sub(
            rf"{re.escape(plain)}(?=(?:[.!?]|$))",
            honorific,
            normalized,
        )
    return normalized


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

    @model_validator(mode="after")
    def normalize_item(self) -> "LearningItem":
        self.title = (
            canonicalize_term_title(self.title)
            if self.type == "term"
            else normalize_honorific_prose(self.title)
        )
        self.explanation = normalize_honorific_prose(self.explanation)
        if not self.title or not self.explanation:
            raise ValueError("학습 항목의 제목과 설명은 비어 있을 수 없습니다.")
        return self


class SummaryTopic(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=800)
    key_points: list[str] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def normalize_style(self) -> "SummaryTopic":
        self.title = self.title.strip()
        self.summary = normalize_honorific_prose(self.summary)
        self.key_points = [
            normalize_honorific_prose(point)
            for point in self.key_points
            if point.strip()
        ]
        return self


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
    deleted_card_ids: list[str] = Field(default_factory=list, max_length=500)
    deleted_note_ids: list[str] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def validate_updates(self) -> "SummaryBatchUpdate":
        if not (
            self.cards
            or self.notes
            or self.deleted_card_ids
            or self.deleted_note_ids
        ):
            raise ValueError("수정할 요약 내용을 입력해 주세요.")
        self.deleted_card_ids = [item.strip() for item in self.deleted_card_ids]
        self.deleted_note_ids = [item.strip() for item in self.deleted_note_ids]
        if any(
            not item or len(item) > 64
            for item in (*self.deleted_card_ids, *self.deleted_note_ids)
        ):
            raise ValueError("삭제할 요약 ID가 올바르지 않습니다.")
        card_ids = [item.id for item in self.cards]
        note_ids = [item.id for item in self.notes]
        if (
            len(card_ids) != len(set(card_ids))
            or len(note_ids) != len(set(note_ids))
            or len(self.deleted_card_ids) != len(set(self.deleted_card_ids))
            or len(self.deleted_note_ids) != len(set(self.deleted_note_ids))
        ):
            raise ValueError("같은 요약을 중복해서 수정할 수 없습니다.")
        if (
            set(card_ids) & set(self.deleted_card_ids)
            or set(note_ids) & set(self.deleted_note_ids)
        ):
            raise ValueError("같은 요약을 동시에 수정하고 삭제할 수 없습니다.")
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

    @model_validator(mode="after")
    def normalize_legacy_generated_style(self) -> "StudyMaterial":
        if self.summary != EMPTY_SUMMARY_TEXT:
            self.summary = normalize_honorific_prose(self.summary)
        self.key_points = [
            normalize_honorific_prose(point)
            for point in self.key_points
            if point.strip()
        ]
        self.keyword_explanations = {
            title: normalize_honorific_prose(explanation)
            for title, explanation in self.keyword_explanations.items()
        }
        return self


class ReferenceDocument(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    name: str = Field(min_length=1, max_length=255)
    text: str = Field(default="", exclude=True)
    uploaded_at: datetime = Field(default_factory=utc_now)


class StudyCategory(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    name: str = Field(min_length=1, max_length=40)
    parent_id: str | None = Field(default=None, max_length=64)
    sort_order: float = Field(default=0, allow_inf_nan=False)
    is_default: bool = False
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def normalize_name(self) -> "StudyCategory":
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("카테고리 이름을 입력해 주세요.")
        return self


class LectureSession(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    session_revision: int = Field(default=0, ge=0)
    title: str = "새 수업"
    title_revision: int = Field(default=0, ge=0, exclude=True)
    summary_notes_revision: int = Field(default=0, ge=0, exclude=True)
    category_revision: int = Field(default=0, ge=0, exclude=True)
    organization_revision: int = Field(default=0, ge=0, exclude=True)
    category_id: str | None = Field(default=None, max_length=64)
    sort_order: float = Field(default=0, allow_inf_nan=False)
    course_name: str = "SKALA Zoom 수업"
    source_type: Literal["zoom", "youtube", "demo"] = "zoom"
    source_url: str | None = Field(default=None, max_length=2_048)
    created_at: datetime = Field(default_factory=utc_now)
    status: Literal["ready", "recording", "completed"] = "ready"
    duration_seconds: float = Field(default=0, ge=0)
    reference_name: str | None = Field(default=None, max_length=255)
    reference_text: str | None = Field(default=None, exclude=True)
    references: list[ReferenceDocument] = Field(default_factory=list, max_length=20)
    segments: list[TranscriptSegment] = Field(default_factory=list)
    material: StudyMaterial = Field(default_factory=StudyMaterial)
    chat_messages: list[ConversationMessage] = Field(default_factory=list)

    @field_serializer("segments")
    def serialize_refined_segments(
        self,
        segments: list[TranscriptSegment],
    ) -> list[dict]:
        """API와 JSON에는 생성 모델 정제를 통과한 전사만 노출합니다."""
        return [
            segment.model_dump(mode="json")
            for segment in segments
            if segment.is_refined
        ]

    def sync_reference_fields(self) -> None:
        """기존 단일 PDF 필드를 여러 PDF 목록과 호환되게 유지합니다."""
        if not self.references and self.reference_name:
            self.references = [
                ReferenceDocument(
                    id=f"legacy-{self.id}",
                    name=self.reference_name,
                    text=self.reference_text or "",
                )
            ]
        self.reference_name = self.references[-1].name if self.references else None
        self.reference_text = (
            "\n\n".join(
                f"[PDF 파일: {reference.name}]\n{reference.text.strip()}"
                for reference in self.references
                if reference.text.strip()
            )
            or None
        )

    @model_validator(mode="after")
    def migrate_legacy_reference(self) -> "LectureSession":
        self.sync_reference_fields()
        return self

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
    category_id: str | None = Field(default=None, max_length=64)
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
    title: str | None = Field(default=None, min_length=1, max_length=100)
    category_id: str | None = Field(default=None, max_length=64)
    sort_order: float | None = Field(default=None, allow_inf_nan=False)

    @model_validator(mode="after")
    def normalize_update(self) -> "SessionUpdate":
        if (
            self.title is None
            and "category_id" not in self.model_fields_set
            and "sort_order" not in self.model_fields_set
        ):
            raise ValueError("수정할 수업 정보를 입력해 주세요.")
        if "sort_order" in self.model_fields_set and self.sort_order is None:
            raise ValueError("올바른 수업 순서를 입력해 주세요.")
        if self.title is not None:
            self.title = self.title.strip()
            if not self.title:
                raise ValueError("수업 제목을 입력해 주세요.")
        return self


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    parent_id: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def normalize_name(self) -> "CategoryCreate":
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("카테고리 이름을 입력해 주세요.")
        return self


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=40)
    parent_id: str | None = Field(default=None, max_length=64)
    sort_order: float | None = Field(default=None, allow_inf_nan=False)

    @model_validator(mode="after")
    def normalize_update(self) -> "CategoryUpdate":
        if (
            self.name is None
            and "parent_id" not in self.model_fields_set
            and "sort_order" not in self.model_fields_set
        ):
            raise ValueError("수정할 레포지토리 정보를 입력해 주세요.")
        if "sort_order" in self.model_fields_set and self.sort_order is None:
            raise ValueError("올바른 레포지토리 순서를 입력해 주세요.")
        if self.name is not None:
            self.name = self.name.strip()
            if not self.name:
                raise ValueError("레포지토리 이름을 입력해 주세요.")
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
    summary_batch_seconds: int | None = Field(default=None, ge=60, le=300)


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


class LlmModelUpdate(BaseModel):
    model: Literal[
        "qwen3.5:0.8b-q8_0",
        "qwen3.5:2b-q4_K_M",
        "qwen3.5:4b-q4_K_M",
        "qwen3.5:9b-q4_K_M",
    ]


class LlmModelResponse(BaseModel):
    model: str
    downloaded: bool = False
