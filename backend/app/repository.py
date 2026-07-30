from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import RLock

from .schemas import ConversationMessage, LectureSession, StudyMaterial, TranscriptSegment


LEGACY_IMPORT_MARKER = "legacy_json_import_v1"
TRANSCRIPT_REFINEMENT_VERSION = 1
MAX_STORED_KEYWORDS = 6


class SessionRepository:
    """Single-user SQLite repository with a one-time legacy JSON import."""

    def __init__(self, database_file: Path, legacy_json_file: Path | None = None):
        self.database_file = database_file
        self.legacy_json_file = legacy_json_file
        self._lock = RLock()
        self._closed = False
        self.database_file.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            self.database_file,
            check_same_thread=False,
            timeout=5,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA synchronous = NORMAL")
        self._connection.execute("PRAGMA busy_timeout = 5000")
        try:
            self._create_schema()
            self._import_legacy_json_once()
            self._compact_persisted_legacy_keywords()
        except Exception:
            self._connection.close()
            self._closed = True
            raise

    def _create_schema(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    title_revision INTEGER NOT NULL DEFAULT 0,
                    course_name TEXT NOT NULL,
                    source_type TEXT NOT NULL
                        CHECK(source_type IN ('zoom', 'youtube', 'demo')),
                    source_url TEXT,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL
                        CHECK(status IN ('ready', 'recording', 'completed')),
                    duration_seconds REAL NOT NULL CHECK(duration_seconds >= 0),
                    reference_name TEXT,
                    reference_text TEXT,
                    references_json TEXT NOT NULL DEFAULT '[]',
                    material_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS segments (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL
                        REFERENCES sessions(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL CHECK(position >= 0),
                    start_seconds REAL NOT NULL CHECK(start_seconds >= 0),
                    speaker TEXT NOT NULL,
                    text TEXT NOT NULL,
                    confidence REAL,
                    raw_text TEXT,
                    is_refined INTEGER NOT NULL DEFAULT 1,
                    UNIQUE(session_id, position)
                );

                CREATE INDEX IF NOT EXISTS idx_sessions_created_at
                    ON sessions(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_segments_session_position
                    ON segments(session_id, position);

                CREATE TABLE IF NOT EXISTS chat_messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL
                        REFERENCES sessions(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL CHECK(position >= 0),
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    text TEXT NOT NULL,
                    class_context TEXT,
                    supplementary_explanation TEXT,
                    knowledge_scope TEXT
                        CHECK(knowledge_scope IN ('class_only', 'class_plus_general')),
                    sources_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    UNIQUE(session_id, position)
                );

                CREATE INDEX IF NOT EXISTS idx_chat_messages_session_position
                    ON chat_messages(session_id, position);

                CREATE TABLE IF NOT EXISTS repository_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            segment_columns = {
                str(row["name"])
                for row in self._connection.execute("PRAGMA table_info(segments)")
            }
            raw_text_missing = "raw_text" not in segment_columns
            refinement_flag_missing = "is_refined" not in segment_columns
            if raw_text_missing:
                self._connection.execute("ALTER TABLE segments ADD COLUMN raw_text TEXT")
            if refinement_flag_missing:
                self._connection.execute(
                    "ALTER TABLE segments ADD COLUMN is_refined INTEGER NOT NULL DEFAULT 0"
                )
            if raw_text_missing:
                self._connection.execute(
                    "UPDATE segments SET raw_text = text WHERE raw_text IS NULL"
                )

            session_columns = {
                str(row["name"])
                for row in self._connection.execute("PRAGMA table_info(sessions)")
            }
            if "reference_name" not in session_columns:
                self._connection.execute(
                    "ALTER TABLE sessions ADD COLUMN reference_name TEXT"
                )
            if "reference_text" not in session_columns:
                self._connection.execute(
                    "ALTER TABLE sessions ADD COLUMN reference_text TEXT"
                )
            if "references_json" not in session_columns:
                self._connection.execute(
                    "ALTER TABLE sessions ADD COLUMN references_json TEXT NOT NULL DEFAULT '[]'"
                )
            if "title_revision" not in session_columns:
                self._connection.execute(
                    "ALTER TABLE sessions ADD COLUMN title_revision INTEGER NOT NULL DEFAULT 0"
                )

    def _import_legacy_json_once(self) -> None:
        if not self.legacy_json_file or not self.legacy_json_file.exists():
            return
        marker = self._connection.execute(
            "SELECT value FROM repository_metadata WHERE key = ?",
            (LEGACY_IMPORT_MARKER,),
        ).fetchone()
        if marker:
            return

        try:
            raw_payload = json.loads(self.legacy_json_file.read_text(encoding="utf-8"))
            if not isinstance(raw_payload, list):
                raise ValueError("최상위 값이 배열이 아닙니다.")
            sessions = []
            for item in raw_payload:
                material = item.get("material") if isinstance(item, dict) else None
                if isinstance(material, dict):
                    self._migrate_material_payload(
                        material,
                        float(item.get("duration_seconds") or 0),
                    )
                sessions.append(LectureSession.model_validate(item))
            session_ids = [session.id for session in sessions]
            if len(session_ids) != len(set(session_ids)):
                raise ValueError("중복된 세션 ID가 있습니다.")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError(
                f"기존 수업 기록을 읽을 수 없습니다: {self.legacy_json_file}. "
                "원본 파일을 확인한 뒤 다시 실행해 주세요."
            ) from exc

        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                for session in sessions:
                    exists = self._connection.execute(
                        "SELECT 1 FROM sessions WHERE id = ?", (session.id,)
                    ).fetchone()
                    if not exists:
                        self._upsert_session(session)
                self._connection.execute(
                    "INSERT INTO repository_metadata(key, value) VALUES (?, ?)",
                    (LEGACY_IMPORT_MARKER, str(len(sessions))),
                )
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise

    def _upsert_session(self, session: LectureSession) -> None:
        session.sync_reference_fields()
        self._compact_legacy_keywords(session.material)
        references_json = json.dumps(
            [
                {
                    "id": reference.id,
                    "name": reference.name,
                    "text": reference.text,
                    "uploaded_at": reference.uploaded_at.isoformat(),
                }
                for reference in session.references
            ],
            ensure_ascii=False,
        )
        self._connection.execute(
            """
            INSERT INTO sessions(
                id, title, title_revision, course_name, source_type, source_url, created_at,
                status, duration_seconds, reference_name, reference_text,
                references_json, material_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                title_revision = excluded.title_revision,
                course_name = excluded.course_name,
                source_type = excluded.source_type,
                source_url = excluded.source_url,
                created_at = excluded.created_at,
                status = excluded.status,
                duration_seconds = excluded.duration_seconds,
                reference_name = excluded.reference_name,
                reference_text = excluded.reference_text,
                references_json = excluded.references_json,
                material_json = excluded.material_json
            """,
            (
                session.id,
                session.title,
                session.title_revision,
                session.course_name,
                session.source_type,
                session.source_url,
                session.created_at.isoformat(),
                session.status,
                session.duration_seconds,
                session.reference_name,
                session.reference_text,
                references_json,
                session.material.model_dump_json(),
            ),
        )

        self._connection.execute(
            "DELETE FROM segments WHERE session_id = ?", (session.id,)
        )
        self._connection.executemany(
            """
            INSERT INTO segments(
                id, session_id, position, start_seconds, speaker, text, confidence,
                raw_text, is_refined
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    segment.id,
                    session.id,
                    position,
                    segment.start_seconds,
                    segment.speaker,
                    segment.text,
                    segment.confidence,
                    segment.raw_text,
                    int(segment.is_refined),
                )
                for position, segment in enumerate(session.segments)
            ],
        )

    @staticmethod
    def _compact_legacy_keywords(material: StudyMaterial) -> None:
        material.keywords = material.keywords[-MAX_STORED_KEYWORDS:]
        material.keyword_explanations = {
            keyword: material.keyword_explanations[keyword]
            for keyword in material.keywords
            if keyword in material.keyword_explanations
        }

    def _compact_persisted_legacy_keywords(self) -> None:
        """기존 API 호환용 keyword 필드만 보수적인 크기로 유지합니다."""
        with self._lock, self._connection:
            rows = self._connection.execute(
                "SELECT id, material_json FROM sessions"
            ).fetchall()
            for row in rows:
                payload = json.loads(row["material_json"])
                keywords = payload.get("keywords")
                if (
                    isinstance(keywords, list)
                    and len(keywords) <= MAX_STORED_KEYWORDS
                ):
                    continue
                material = StudyMaterial.model_validate(payload)
                self._compact_legacy_keywords(material)
                self._connection.execute(
                    "UPDATE sessions SET material_json = ? WHERE id = ?",
                    (material.model_dump_json(), row["id"]),
                )

    @staticmethod
    def _migrate_material_payload(payload: dict, duration_seconds: float) -> None:
        if int(payload.get("transcript_refinement_version") or 0) >= TRANSCRIPT_REFINEMENT_VERSION:
            return
        # 구버전 학습 항목은 원시 STT에서 추출됐을 수 있으므로 화면에서 제거합니다.
        payload["learning_items"] = []
        payload["keywords"] = []
        payload["keyword_explanations"] = {}
        payload["learning_items_processed_through_seconds"] = max(
            float(payload.get("learning_items_processed_through_seconds") or 0),
            duration_seconds,
        )
        payload["transcript_refinement_version"] = TRANSCRIPT_REFINEMENT_VERSION

    def _session_from_row(self, row: sqlite3.Row) -> LectureSession:
        segment_rows = self._connection.execute(
            """
            SELECT id, start_seconds, speaker, text, confidence, raw_text, is_refined
            FROM segments
            WHERE session_id = ?
            ORDER BY position ASC
            """,
            (row["id"],),
        ).fetchall()
        chat_rows = self._connection.execute(
            """
            SELECT id, role, text, class_context, supplementary_explanation,
                   knowledge_scope, sources_json, created_at
            FROM chat_messages
            WHERE session_id = ?
            ORDER BY position ASC
            """,
            (row["id"],),
        ).fetchall()
        material_payload = json.loads(row["material_json"])
        self._migrate_material_payload(material_payload, float(row["duration_seconds"]))
        references_payload = json.loads(row["references_json"] or "[]")
        return LectureSession(
            id=row["id"],
            title=row["title"],
            title_revision=row["title_revision"],
            course_name=row["course_name"],
            source_type=row["source_type"],
            source_url=row["source_url"],
            created_at=row["created_at"],
            status=row["status"],
            duration_seconds=row["duration_seconds"],
            reference_name=row["reference_name"],
            reference_text=row["reference_text"],
            references=references_payload,
            material=StudyMaterial.model_validate(material_payload),
            segments=[TranscriptSegment.model_validate(dict(item)) for item in segment_rows],
            chat_messages=[
                ConversationMessage(
                    id=item["id"],
                    role=item["role"],
                    text=item["text"],
                    class_context=item["class_context"],
                    supplementary_explanation=item["supplementary_explanation"],
                    knowledge_scope=item["knowledge_scope"],
                    sources=json.loads(item["sources_json"]),
                    created_at=item["created_at"],
                )
                for item in chat_rows
            ],
        )

    def list(self) -> list[LectureSession]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM sessions ORDER BY created_at DESC"
            ).fetchall()
            return [self._session_from_row(row) for row in rows]

    def get(self, session_id: str) -> LectureSession | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            return self._session_from_row(row) if row else None

    def save(self, session: LectureSession) -> LectureSession:
        snapshot = session.model_copy(deep=True)
        with self._lock, self._connection:
            self._merge_newer_persisted_state(snapshot)
            self._upsert_session(snapshot)
        return snapshot.model_copy(deep=True)

    def _merge_newer_persisted_state(self, snapshot: LectureSession) -> None:
        """오래 실행된 백그라운드 작업이 최신 사용자 상태를 되돌리지 않게 합니다."""
        row = self._connection.execute(
            "SELECT title, title_revision, material_json FROM sessions WHERE id = ?",
            (snapshot.id,),
        ).fetchone()
        if not row:
            return

        persisted_title_revision = int(row["title_revision"] or 0)
        if persisted_title_revision > snapshot.title_revision:
            snapshot.title = row["title"]
            snapshot.title_revision = persisted_title_revision

        persisted_material = StudyMaterial.model_validate(json.loads(row["material_json"]))
        persisted_quiz_at = persisted_material.quiz_generated_at
        incoming_quiz_at = snapshot.material.quiz_generated_at
        persisted_quiz_is_newer = persisted_quiz_at is not None and (
            incoming_quiz_at is None
            or persisted_quiz_at > incoming_quiz_at
            or (
                persisted_quiz_at == incoming_quiz_at
                and bool(persisted_material.quiz_questions)
                and not snapshot.material.quiz_questions
            )
        )
        if persisted_quiz_is_newer:
            snapshot.material.quiz_questions = [
                question.model_copy(deep=True)
                for question in persisted_material.quiz_questions
            ]
            snapshot.material.quiz_generated_at = persisted_quiz_at

    def append_chat_messages(
        self,
        session_id: str,
        messages: list[ConversationMessage],
    ) -> None:
        if not messages:
            return
        snapshots = [message.model_copy(deep=True) for message in messages]
        with self._lock, self._connection:
            next_position = self._connection.execute(
                """
                SELECT COALESCE(MAX(position) + 1, 0)
                FROM chat_messages
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()[0]
            self._connection.executemany(
                """
                INSERT INTO chat_messages(
                    id, session_id, position, role, text, class_context,
                    supplementary_explanation, knowledge_scope, sources_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        message.id,
                        session_id,
                        next_position + offset,
                        message.role,
                        message.text,
                        message.class_context,
                        message.supplementary_explanation,
                        message.knowledge_scope,
                        json.dumps(
                            [source.model_dump(mode="json") for source in message.sources],
                            ensure_ascii=False,
                        ),
                        message.created_at.isoformat(),
                    )
                    for offset, message in enumerate(snapshots)
                ],
            )

    def delete(self, session_id: str) -> bool:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "DELETE FROM sessions WHERE id = ?", (session_id,)
            )
        return cursor.rowcount > 0

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._connection.close()
                self._closed = True
