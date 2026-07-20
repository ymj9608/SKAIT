import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pydantic import ValidationError

from app.repository import LEGACY_IMPORT_MARKER, SessionRepository
from app.schemas import LectureSession, SessionCreate, StudyMaterial, TranscriptSegment


def sample_session(session_id: str = "session-1", title: str = "테스트 수업") -> LectureSession:
    return LectureSession(
        id=session_id,
        title=title,
        course_name="SKALA",
        source_type="youtube",
        source_url="https://youtu.be/WsPJ8FsoMcU",
        status="completed",
        duration_seconds=61.5,
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
            review_questions=["콜백 함수란 무엇인가요?"],
        ),
    )


class SessionRepositoryTests(unittest.TestCase):
    def test_save_close_and_reopen_preserves_the_complete_session(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "reclass.sqlite3"
            original = sample_session()

            repository = SessionRepository(database)
            repository.save(original)
            repository.close()

            reopened = SessionRepository(database)
            restored = reopened.get(original.id)
            reopened.close()

            self.assertEqual(restored, original)

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
    def test_youtube_session_requires_an_allowed_https_url(self) -> None:
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
