import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pydantic import ValidationError

from app.repository import (
    LEGACY_IMPORT_MARKER,
    SessionRepository,
    migrate_legacy_database,
)
from app.schemas import (
    ConversationMessage,
    LearningItem,
    LectureSession,
    QuizQuestion,
    ReferenceDocument,
    SessionCreate,
    StudyCategory,
    StudyMaterial,
    SummaryNote,
    SourceReference,
    TranscriptSegment,
    utc_now,
)


def sample_session(session_id: str = "session-1", title: str = "테스트 수업") -> LectureSession:
    return LectureSession(
        id=session_id,
        title=title,
        course_name="SKALA",
        source_type="youtube",
        source_url="https://youtu.be/WsPJ8FsoMcU",
        status="completed",
        duration_seconds=61.5,
        reference_name="javascript-basics.pdf",
        reference_text="콜백 함수와 lexical this를 설명하는 수업 자료입니다.",
        segments=[
            TranscriptSegment(
                id=f"{session_id}-segment-1",
                start_seconds=0,
                speaker="강사",
                text="자바스크립트 함수의 활용을 설명합니다.",
                confidence=None,
            ),
            TranscriptSegment(
                id=f"{session_id}-segment-2",
                start_seconds=30,
                speaker="강사",
                text="콜백 함수와 this를 살펴봅니다.",
                confidence=0.94,
            ),
        ],
        material=StudyMaterial(
            summary="자바스크립트 함수 활용 수업입니다.",
            key_points=["함수는 값처럼 전달할 수 있습니다."],
            keywords=["함수", "콜백"],
            keyword_explanations={
                "콜백": "다른 함수에 인자로 전달되어 나중에 실행되는 함수입니다."
            },
            learning_items=[
                LearningItem(
                    type="term",
                    title="콜백",
                    explanation="다른 함수에 인자로 전달되어 나중에 실행되는 함수입니다.",
                )
            ],
            review_questions=["콜백 함수란 무엇인가요?"],
        ),
    )


class SessionRepositoryTests(unittest.TestCase):
    def test_fresh_repository_has_default_my_lessons_category(self) -> None:
        with TemporaryDirectory() as directory:
            repository = SessionRepository(Path(directory) / "skait.sqlite3")

            categories = repository.list_categories()
            saved = repository.save(sample_session())
            repository.close()

            self.assertEqual(len(categories), 1)
            self.assertEqual(categories[0].name, "내 수업")
            self.assertTrue(categories[0].is_default)
            self.assertEqual(saved.category_id, categories[0].id)

    def test_categories_and_session_assignments_survive_restart(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "skait.sqlite3"
            repository = SessionRepository(database)
            category = repository.create_category(StudyCategory(name="백엔드 개발"))
            session = sample_session()
            session.category_id = category.id
            session.category_revision += 1
            repository.save(session)
            repository.close()

            reopened = SessionRepository(database)
            restored_category = reopened.get_category(category.id)
            restored_session = reopened.get(session.id)
            reopened.close()

            self.assertEqual(restored_category.name, "백엔드 개발")
            self.assertEqual(restored_session.category_id, category.id)

    def test_manual_session_order_survives_restart_and_stale_background_saves(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "skait.sqlite3"
            repository = SessionRepository(database)
            saved = repository.save(sample_session())
            stale_background_snapshot = repository.get(saved.id)

            reordered = repository.get(saved.id)
            reordered.sort_order = -7.5
            reordered.organization_revision += 1
            repository.save(reordered)

            stale_background_snapshot.duration_seconds = 90
            merged = repository.save(stale_background_snapshot)
            repository.close()

            reopened = SessionRepository(database)
            restored = reopened.get(saved.id)
            reopened.close()

            self.assertEqual(merged.sort_order, -7.5)
            self.assertEqual(restored.sort_order, -7.5)
            self.assertEqual(restored.duration_seconds, 90)

    def test_deleting_root_category_moves_sessions_to_default_category(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "skait.sqlite3"
            repository = SessionRepository(database)
            default_category = repository.default_category()
            category = repository.create_category(StudyCategory(name="자격증"))
            session = sample_session()
            session.category_id = category.id
            session.category_revision += 1
            saved = repository.save(session)
            stale_background_snapshot = repository.get(session.id)

            self.assertTrue(repository.delete_category(category.id))
            self.assertEqual(
                repository.get(session.id).category_id,
                default_category.id,
            )

            stale_background_snapshot.duration_seconds = 90
            merged = repository.save(stale_background_snapshot)
            repository.close()

            self.assertEqual(merged.category_id, default_category.id)
            self.assertGreater(merged.category_revision, saved.category_revision)
            self.assertEqual(merged.duration_seconds, 90)

    def test_existing_uncategorized_sessions_are_migrated_to_default_category(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "skait.sqlite3"
            repository = SessionRepository(database)
            saved = repository.save(sample_session())
            repository.close()

            connection = sqlite3.connect(database)
            connection.execute(
                "UPDATE sessions SET category_id = NULL WHERE id = ?",
                (saved.id,),
            )
            connection.commit()
            connection.close()

            migrated = SessionRepository(database)
            default_category = migrated.default_category()
            restored = migrated.get(saved.id)
            migrated.close()

            self.assertEqual(restored.category_id, default_category.id)

    def test_default_category_can_be_renamed_but_not_deleted(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "skait.sqlite3"
            repository = SessionRepository(database)
            default_category = repository.default_category()

            renamed = repository.update_category(default_category.id, "SKALA 수업")
            with self.assertRaisesRegex(ValueError, "삭제할 수 없습니다"):
                repository.delete_category(default_category.id)
            repository.close()

            reopened = SessionRepository(database)
            restored = reopened.default_category()
            saved = reopened.save(sample_session())
            reopened.close()

            self.assertEqual(renamed.name, "SKALA 수업")
            self.assertEqual(restored.name, "SKALA 수업")
            self.assertTrue(restored.is_default)
            self.assertEqual(saved.category_id, restored.id)

    def test_category_can_move_under_another_category_or_become_independent(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "skait.sqlite3"
            repository = SessionRepository(database)
            first = repository.create_category(StudyCategory(name="첫 번째"))
            second = repository.create_category(StudyCategory(name="두 번째"))

            nested = repository.update_category(
                first.id,
                parent_id=second.id,
                update_parent=True,
            )
            independent = repository.update_category(
                first.id,
                parent_id=None,
                update_parent=True,
            )
            repository.close()

            reopened = SessionRepository(database)
            restored = reopened.get_category(first.id)
            reopened.close()

            self.assertEqual(nested.parent_id, second.id)
            self.assertIsNone(independent.parent_id)
            self.assertIsNone(restored.parent_id)

    def test_sibling_category_order_survives_restart(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "skait.sqlite3"
            repository = SessionRepository(database)
            parent = repository.create_category(StudyCategory(name="상위"))
            first = repository.create_category(
                StudyCategory(name="첫 번째", parent_id=parent.id)
            )
            second = repository.create_category(
                StudyCategory(name="두 번째", parent_id=parent.id)
            )

            reordered = repository.update_category(
                second.id,
                sort_order=first.sort_order - 1,
            )
            repository.close()

            reopened = SessionRepository(database)
            siblings = [
                category
                for category in reopened.list_categories()
                if category.parent_id == parent.id
            ]
            reopened.close()

            self.assertLess(reordered.sort_order, first.sort_order)
            self.assertEqual(
                [category.id for category in siblings],
                [second.id, first.id],
            )

    def test_category_cannot_move_into_itself_or_its_descendant(self) -> None:
        with TemporaryDirectory() as directory:
            repository = SessionRepository(Path(directory) / "skait.sqlite3")
            parent = repository.create_category(StudyCategory(name="상위"))
            child = repository.create_category(
                StudyCategory(name="하위", parent_id=parent.id)
            )

            with self.assertRaisesRegex(ValueError, "하위 레포지토리"):
                repository.update_category(
                    parent.id,
                    parent_id=child.id,
                    update_parent=True,
                )
            with self.assertRaisesRegex(ValueError, "자기 자신"):
                repository.update_category(
                    parent.id,
                    parent_id=parent.id,
                    update_parent=True,
                )

            restored = repository.get_category(parent.id)
            repository.close()

            self.assertIsNone(restored.parent_id)

    def test_default_category_move_survives_restart(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "skait.sqlite3"
            repository = SessionRepository(database)
            default_category = repository.default_category()
            parent = repository.create_category(StudyCategory(name="전체 수업"))
            repository.update_category(
                default_category.id,
                parent_id=parent.id,
                update_parent=True,
            )
            repository.close()

            reopened = SessionRepository(database)
            restored = reopened.default_category()
            reopened.close()

            self.assertEqual(restored.parent_id, parent.id)

    def test_nested_categories_survive_restart_and_are_promoted_when_parent_is_deleted(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "skait.sqlite3"
            repository = SessionRepository(database)
            parent = repository.create_category(StudyCategory(name="개발"))
            child = repository.create_category(
                StudyCategory(name="백엔드", parent_id=parent.id)
            )
            grandchild = repository.create_category(
                StudyCategory(name="Spring", parent_id=child.id)
            )
            session = sample_session()
            session.category_id = child.id
            session.category_revision += 1
            repository.save(session)
            repository.close()

            reopened = SessionRepository(database)
            restored = {category.id: category for category in reopened.list_categories()}
            self.assertEqual(restored[child.id].parent_id, parent.id)
            self.assertEqual(restored[grandchild.id].parent_id, child.id)

            self.assertTrue(reopened.delete_category(child.id))
            promoted = {category.id: category for category in reopened.list_categories()}
            promoted_session = reopened.get(session.id)
            reopened.close()

            self.assertNotIn(child.id, promoted)
            self.assertEqual(promoted[grandchild.id].parent_id, parent.id)
            self.assertEqual(promoted_session.category_id, parent.id)

    def test_existing_flat_category_table_is_migrated_without_data_loss(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "skait.sqlite3"
            repository = SessionRepository(database)
            category = repository.create_category(StudyCategory(name="기존 카테고리"))
            repository.close()

            connection = sqlite3.connect(database)
            connection.execute("DROP INDEX idx_categories_parent_created_at")
            connection.execute("DROP INDEX idx_categories_parent_sort_order")
            connection.execute("ALTER TABLE categories DROP COLUMN parent_id")
            connection.execute("ALTER TABLE categories DROP COLUMN sort_order")
            connection.commit()
            connection.close()

            migrated = SessionRepository(database)
            restored = migrated.get_category(category.id)
            migrated.close()

            self.assertEqual(restored.name, "기존 카테고리")
            self.assertIsNone(restored.parent_id)

    def test_legacy_database_is_renamed_without_losing_sessions(self) -> None:
        with TemporaryDirectory() as directory:
            directory_path = Path(directory)
            legacy_database = directory_path / "reclass.sqlite3"
            database = directory_path / "skait.sqlite3"
            repository = SessionRepository(legacy_database)
            repository.save(sample_session())
            repository.close()

            self.assertTrue(migrate_legacy_database(database))
            self.assertFalse(legacy_database.exists())
            self.assertTrue(database.exists())

            migrated = SessionRepository(database)
            self.assertEqual(migrated.get("session-1").title, "테스트 수업")
            self.assertEqual(len(migrated.get("session-1").segments), 2)
            migrated.close()

    def test_existing_skait_database_is_never_overwritten_by_legacy_database(self) -> None:
        with TemporaryDirectory() as directory:
            directory_path = Path(directory)
            legacy_database = directory_path / "reclass.sqlite3"
            database = directory_path / "skait.sqlite3"

            legacy = SessionRepository(legacy_database)
            legacy.save(sample_session(title="이전 DB 수업"))
            legacy.close()
            current = SessionRepository(database)
            current.save(sample_session(title="현재 DB 수업"))
            current.close()

            self.assertFalse(migrate_legacy_database(database))
            self.assertTrue(legacy_database.exists())

            reopened = SessionRepository(database)
            self.assertEqual(reopened.get("session-1").title, "현재 DB 수업")
            reopened.close()

    def test_custom_database_path_does_not_claim_the_legacy_default_database(self) -> None:
        with TemporaryDirectory() as directory:
            directory_path = Path(directory)
            legacy_database = directory_path / "reclass.sqlite3"
            custom_database = directory_path / "custom.sqlite3"
            legacy_database.touch()

            self.assertFalse(migrate_legacy_database(custom_database))
            self.assertTrue(legacy_database.exists())
            self.assertFalse(custom_database.exists())

    def test_all_learning_items_are_preserved_during_storage(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "reclass.sqlite3"
            repository = SessionRepository(database)
            session = sample_session()
            session.material.learning_items = [
                LearningItem(
                    type="term",
                    title=f"용어 {index}",
                    explanation=f"핵심 용어 {index}의 설명입니다.",
                )
                for index in range(15)
            ]
            saved = repository.save(session)
            restored = repository.get(session.id)
            repository.close()
            reopened = SessionRepository(database)
            restored_after_restart = reopened.get(session.id)
            reopened.close()

            self.assertEqual(len(saved.material.learning_items), 15)
            self.assertEqual(len(restored.material.learning_items), 15)
            self.assertEqual(len(restored_after_restart.material.learning_items), 15)
            self.assertEqual(saved.material.learning_items[0].title, "용어 0")
            self.assertLessEqual(len(saved.material.keywords), 6)

    def test_stale_background_save_preserves_newer_title_and_quiz(self) -> None:
        with TemporaryDirectory() as directory:
            repository = SessionRepository(Path(directory) / "reclass.sqlite3")
            session = repository.save(sample_session())
            stale_background_snapshot = repository.get(session.id)

            updated = repository.get(session.id)
            updated.title = "사용자가 수정한 제목"
            updated.title_revision += 1
            updated.material.quiz_questions = [
                QuizQuestion(
                    id="latest-quiz",
                    question="콜백 함수의 특징으로 맞는 것은?",
                    options=[
                        "다른 함수에 전달될 수 있다.",
                        "항상 즉시 실행된다.",
                        "인자를 받을 수 없다.",
                        "반환값을 만들 수 없다.",
                    ],
                    correct_option_index=0,
                    explanation="요약에서는 콜백을 다른 함수에 전달되는 함수로 설명합니다.",
                )
            ]
            updated.material.quiz_generated_at = utc_now()
            repository.save(updated)

            stale_background_snapshot.duration_seconds = 90
            saved = repository.save(stale_background_snapshot)
            repository.close()

            self.assertEqual(saved.title, "사용자가 수정한 제목")
            self.assertEqual(saved.material.quiz_questions[0].id, "latest-quiz")
            self.assertEqual(saved.duration_seconds, 90)

    def test_stale_background_save_preserves_newer_personal_summary_note(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "skait.sqlite3"
            repository = SessionRepository(database)
            session = repository.save(sample_session())
            stale_background_snapshot = repository.get(session.id)

            updated = repository.get(session.id)
            updated.material.summary_notes.append(
                SummaryNote(id="latest-note", text="JPA 시작")
            )
            updated.summary_notes_revision += 1
            repository.save(updated)

            stale_background_snapshot.duration_seconds = 90
            saved = repository.save(stale_background_snapshot)
            repository.close()

            reopened = SessionRepository(database)
            restored = reopened.get(session.id)
            reopened.close()

            self.assertEqual(saved.summary_notes_revision, 1)
            self.assertEqual(
                [note.text for note in saved.material.summary_notes],
                ["JPA 시작"],
            )
            self.assertEqual(
                [note.text for note in restored.material.summary_notes],
                ["JPA 시작"],
            )

    def test_stale_background_save_does_not_restore_deleted_personal_summary_note(self) -> None:
        with TemporaryDirectory() as directory:
            repository = SessionRepository(Path(directory) / "skait.sqlite3")
            session = sample_session()
            session.material.summary_notes.append(
                SummaryNote(id="deleted-note", text="삭제할 직접 요약")
            )
            session = repository.save(session)
            stale_background_snapshot = repository.get(session.id)

            updated = repository.get(session.id)
            updated.material.summary_notes = []
            updated.summary_notes_revision += 1
            repository.save(updated)

            saved = repository.save(stale_background_snapshot)
            repository.close()

            self.assertEqual(saved.summary_notes_revision, 1)
            self.assertEqual(saved.material.summary_notes, [])

    def test_chat_messages_survive_session_saves_and_restarts(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "reclass.sqlite3"
            session = sample_session()
            repository = SessionRepository(database)
            session = repository.save(session)
            stale_background_snapshot = repository.get(session.id)
            repository.append_chat_messages(
                session.id,
                [
                    ConversationMessage(role="user", text="콜백 함수가 뭐야?"),
                    ConversationMessage(
                        role="assistant",
                        text="다른 함수에 전달되는 함수입니다.",
                        class_context="수업에서 콜백 함수를 설명했습니다.",
                        knowledge_scope="class_only",
                        sources=[
                            SourceReference(
                                segment_id=session.segments[1].id,
                                start_seconds=30,
                                speaker="강사",
                                excerpt=session.segments[1].text,
                            )
                        ],
                    ),
                ],
            )

            # 대화 생성 전 시작된 백그라운드 저장도 최신 대화를 반환해야 합니다.
            saved = repository.save(stale_background_snapshot)
            repository.close()

            reopened = SessionRepository(database)
            restored = reopened.get(session.id)
            reopened.close()

            self.assertEqual(
                [message.role for message in saved.chat_messages],
                ["user", "assistant"],
            )
            self.assertEqual(
                [message.role for message in restored.chat_messages],
                ["user", "assistant"],
            )
            self.assertEqual(restored.chat_messages[0].text, "콜백 함수가 뭐야?")
            self.assertEqual(
                restored.chat_messages[1].sources[0].segment_id,
                session.segments[1].id,
            )

    def test_old_raw_segments_and_learning_items_are_migrated_safely(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "reclass.sqlite3"
            connection = sqlite3.connect(database)
            connection.executescript(
                """
                CREATE TABLE sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    course_name TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_url TEXT,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    duration_seconds REAL NOT NULL,
                    material_json TEXT NOT NULL
                );
                CREATE TABLE segments (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    start_seconds REAL NOT NULL,
                    speaker TEXT NOT NULL,
                    text TEXT NOT NULL,
                    confidence REAL
                );
                """
            )
            old_material = {
                "summary": "가격 평균을 설명한 구간입니다.",
                "learning_items": [
                    {
                        "type": "term",
                        "title": "프라이스 와이 언더버 트렌",
                        "explanation": "원시 STT에서 잘못 뽑힌 용어입니다.",
                    }
                ],
                "keywords": ["프라이스 와이 언더버 트렌"],
                "keyword_explanations": {
                    "프라이스 와이 언더버 트렌": "잘못된 설명"
                },
            }
            connection.execute(
                """
                INSERT INTO sessions(
                    id, title, course_name, source_type, source_url, created_at,
                    status, duration_seconds, material_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "old-session",
                    "기존 수업",
                    "SKALA",
                    "zoom",
                    None,
                    "2026-07-21T00:00:00+00:00",
                    "completed",
                    120,
                    json.dumps(old_material, ensure_ascii=False),
                ),
            )
            connection.execute(
                """
                INSERT INTO segments(
                    id, session_id, position, start_seconds, speaker, text, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "old-segment",
                    "old-session",
                    0,
                    0,
                    "교수님",
                    "프라이스 와이 언더버 트렌",
                    0.8,
                ),
            )
            connection.commit()
            connection.close()

            repository = SessionRepository(database)
            restored = repository.get("old-session")
            repository.close()

            self.assertEqual(restored.segments[0].raw_text, "프라이스 와이 언더버 트렌")
            self.assertFalse(restored.segments[0].is_refined)
            self.assertEqual(restored.material.learning_items, [])
            self.assertEqual(restored.material.keywords, [])
            self.assertEqual(restored.material.keyword_explanations, {})
            self.assertEqual(
                restored.material.learning_items_processed_through_seconds,
                120,
            )

    def test_personal_summary_note_is_persistent(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "reclass.sqlite3"
            session = sample_session()
            session.material.summary_notes.append(
                SummaryNote(text="요청 검증 흐름을 다시 복습하기")
            )

            repository = SessionRepository(database)
            repository.save(session)
            repository.close()

            reopened = SessionRepository(database)
            restored = reopened.get(session.id)
            reopened.close()

            self.assertEqual(
                restored.material.summary_notes[0].text,
                "요청 검증 흐름을 다시 복습하기",
            )

    def test_multiple_pdf_references_survive_restart_without_exposing_text(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "reclass.sqlite3"
            session = sample_session()
            session.references.append(
                ReferenceDocument(
                    id="reference-2",
                    name="fastapi-routing.pdf",
                    text="FastAPI 경로 함수와 APIRouter를 설명합니다.",
                )
            )

            repository = SessionRepository(database)
            repository.save(session)
            repository.close()

            reopened = SessionRepository(database)
            restored = reopened.get(session.id)
            reopened.close()

            self.assertEqual(
                [reference.name for reference in restored.references],
                ["javascript-basics.pdf", "fastapi-routing.pdf"],
            )
            self.assertIn("lexical this", restored.reference_text)
            self.assertIn("APIRouter", restored.reference_text)
            serialized = restored.model_dump(mode="json")
            self.assertNotIn("text", serialized["references"][0])
            self.assertNotIn("reference_text", serialized)

    def test_raw_and_refined_transcript_are_stored_but_raw_is_not_serialized(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "reclass.sqlite3"
            session = sample_session()
            session.segments[0].raw_text = "와이 언더바 트레인의 평균"
            session.segments[0].text = "`y_train`의 평균"
            session.segments[0].is_refined = True

            repository = SessionRepository(database)
            repository.save(session)
            repository.close()

            reopened = SessionRepository(database)
            restored = reopened.get(session.id)
            reopened.close()

            self.assertEqual(restored.segments[0].raw_text, "와이 언더바 트레인의 평균")
            self.assertEqual(restored.segments[0].text, "`y_train`의 평균")
            serialized = restored.model_dump(mode="json")
            self.assertNotIn("raw_text", serialized["segments"][0])
            self.assertNotIn("is_refined", serialized["segments"][0])

    def test_unrefined_segment_is_completely_hidden_from_serialized_session(self) -> None:
        session = sample_session()
        session.segments.insert(
            0,
            TranscriptSegment(
                text="프라이스 와이 언더버 트렌",
                raw_text="프라이스 와이 언더버 트렌",
                is_refined=False,
            ),
        )

        serialized = session.model_dump(mode="json")

        self.assertEqual(len(serialized["segments"]), 2)
        self.assertNotIn(
            "프라이스 와이 언더버 트렌",
            [segment["text"] for segment in serialized["segments"]],
        )

    def test_save_close_and_reopen_preserves_the_complete_session(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "reclass.sqlite3"
            original = sample_session()

            repository = SessionRepository(database)
            saved = repository.save(original)
            repository.close()

            reopened = SessionRepository(database)
            restored = reopened.get(original.id)
            reopened.close()

            self.assertEqual(saved.session_revision, 1)
            self.assertEqual(restored, saved)

    def test_session_revision_increases_with_every_persisted_update(self) -> None:
        with TemporaryDirectory() as directory:
            repository = SessionRepository(Path(directory) / "skait.sqlite3")
            first = repository.save(sample_session())
            second = repository.save(first)
            third = repository.save(second)
            repository.close()

            self.assertEqual(
                [first.session_revision, second.session_revision, third.session_revision],
                [1, 2, 3],
            )

    def test_existing_database_adds_optional_pdf_columns_without_data_loss(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "reclass.sqlite3"
            connection = sqlite3.connect(database)
            connection.execute(
                """
                CREATE TABLE sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    course_name TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_url TEXT,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    duration_seconds REAL NOT NULL,
                    material_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "legacy-session",
                    "기존 수업",
                    "SKALA",
                    "zoom",
                    None,
                    "2026-07-21T00:00:00+00:00",
                    "ready",
                    0,
                    StudyMaterial().model_dump_json(),
                ),
            )
            connection.commit()
            connection.close()

            repository = SessionRepository(database)
            restored = repository.get("legacy-session")
            self.assertEqual(restored.title, "기존 수업")
            self.assertIsNone(restored.reference_name)
            restored.reference_name = "lecture.pdf"
            restored.reference_text = "train set과 test set을 설명합니다."
            repository.save(restored)
            repository.close()

            reopened = SessionRepository(database)
            persisted = reopened.get("legacy-session")
            reopened.close()
            self.assertEqual(persisted.reference_name, "lecture.pdf")
            self.assertIn("train set", persisted.reference_text)
            self.assertEqual(
                [reference.name for reference in persisted.references],
                ["lecture.pdf"],
            )

    def test_existing_single_pdf_is_migrated_to_the_reference_list(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "reclass.sqlite3"
            connection = sqlite3.connect(database)
            connection.execute(
                """
                CREATE TABLE sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    course_name TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_url TEXT,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    duration_seconds REAL NOT NULL,
                    reference_name TEXT,
                    reference_text TEXT,
                    material_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "legacy-pdf-session",
                    "기존 PDF 수업",
                    "SKALA",
                    "zoom",
                    None,
                    "2026-07-21T00:00:00+00:00",
                    "ready",
                    0,
                    "legacy-reference.pdf",
                    "기존 PDF의 train set 설명",
                    StudyMaterial().model_dump_json(),
                ),
            )
            connection.commit()
            connection.close()

            repository = SessionRepository(database)
            restored = repository.get("legacy-pdf-session")
            repository.save(restored)
            repository.close()

            reopened = SessionRepository(database)
            persisted = reopened.get("legacy-pdf-session")
            reopened.close()

            self.assertEqual(len(persisted.references), 1)
            self.assertEqual(persisted.references[0].id, "legacy-legacy-pdf-session")
            self.assertEqual(persisted.references[0].name, "legacy-reference.pdf")
            self.assertIn("train set", persisted.reference_text)

    def test_update_and_delete_are_persistent(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "reclass.sqlite3"
            repository = SessionRepository(database)
            session = sample_session()
            repository.save(session)
            session.title = "수정된 제목"
            session.segments = session.segments[:1]
            repository.save(session)
            repository.close()

            reopened = SessionRepository(database)
            self.assertEqual(reopened.get(session.id).title, "수정된 제목")
            self.assertEqual(len(reopened.get(session.id).segments), 1)
            self.assertTrue(reopened.delete(session.id))
            reopened.close()

            final = SessionRepository(database)
            self.assertIsNone(final.get(session.id))
            final.close()

    def test_legacy_json_is_imported_once_without_overwriting_database(self) -> None:
        with TemporaryDirectory() as directory:
            directory_path = Path(directory)
            database = directory_path / "reclass.sqlite3"
            legacy = directory_path / "sessions.json"

            existing = sample_session(title="DB가 우선인 제목")
            repository = SessionRepository(database)
            repository.save(existing)
            repository.close()

            legacy_sessions = [
                sample_session(title="JSON이 덮어쓰면 안 되는 제목"),
                sample_session("session-2", "가져올 예전 수업"),
            ]
            legacy.write_text(
                json.dumps(
                    [item.model_dump(mode="json") for item in legacy_sessions],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            migrated = SessionRepository(database, legacy)
            self.assertEqual(migrated.get("session-1").title, "DB가 우선인 제목")
            self.assertEqual(migrated.get("session-2").title, "가져올 예전 수업")
            self.assertEqual(len(migrated.list()), 2)
            migrated.close()

            legacy.write_text("[]", encoding="utf-8")
            reopened = SessionRepository(database, legacy)
            self.assertEqual(len(reopened.list()), 2)
            reopened.close()
            self.assertTrue(legacy.exists())

            connection = sqlite3.connect(database)
            marker = connection.execute(
                "SELECT value FROM repository_metadata WHERE key = ?",
                (LEGACY_IMPORT_MARKER,),
            ).fetchone()
            connection.close()
            self.assertEqual(marker[0], "2")

    def test_invalid_legacy_json_never_partially_imports(self) -> None:
        with TemporaryDirectory() as directory:
            directory_path = Path(directory)
            database = directory_path / "reclass.sqlite3"
            legacy = directory_path / "sessions.json"
            valid = sample_session().model_dump(mode="json")
            legacy.write_text(
                json.dumps([valid, {"id": "broken", "segments": [{"text": ""}]}]),
                encoding="utf-8",
            )

            with self.assertRaises(RuntimeError):
                SessionRepository(database, legacy)

            repository = SessionRepository(database)
            self.assertEqual(repository.list(), [])
            repository.close()
            self.assertTrue(legacy.exists())

            connection = sqlite3.connect(database)
            marker = connection.execute(
                "SELECT value FROM repository_metadata WHERE key = ?",
                (LEGACY_IMPORT_MARKER,),
            ).fetchone()
            connection.close()
            self.assertIsNone(marker)


class SessionSourceValidationTests(unittest.TestCase):
    def test_youtube_session_allows_no_url_and_validates_a_provided_url(self) -> None:
        without_url = SessionCreate(
            title="YouTube 수업",
            source_type="youtube",
        )
        self.assertIsNone(without_url.source_url)

        payload = SessionCreate(
            title="YouTube 수업",
            source_type="youtube",
            source_url="https://youtu.be/WsPJ8FsoMcU",
        )
        self.assertEqual(payload.source_type, "youtube")

        for url in (
            "http://youtu.be/WsPJ8FsoMcU",
            "https://youtube.example.com/watch?v=test",
            "javascript:alert(1)",
        ):
            with self.subTest(url=url), self.assertRaises(ValidationError):
                SessionCreate(title="잘못된 주소", source_type="youtube", source_url=url)

    def test_zoom_session_discards_an_unneeded_source_url(self) -> None:
        payload = SessionCreate(
            title="Zoom 수업",
            source_type="zoom",
            source_url="https://youtu.be/ignored",
        )
        self.assertIsNone(payload.source_url)


if __name__ == "__main__":
    unittest.main()
