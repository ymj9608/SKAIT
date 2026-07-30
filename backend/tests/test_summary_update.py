import asyncio
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.main import add_summary_note, update_summaries
from app.schemas import (
    LectureSession,
    StudyMaterial,
    SummaryBatchUpdate,
    SummaryCard,
    SummaryNote,
    SummaryNoteCreate,
    SummaryTopic,
)


class RecordingRepository:
    def __init__(self) -> None:
        self.saved: LectureSession | None = None

    def save(self, session: LectureSession) -> LectureSession:
        self.saved = session.model_copy(deep=True)
        return self.saved


class SummaryUpdateApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.card = SummaryCard(
            id="card-1",
            start_seconds=0,
            end_seconds=120,
            topics=[
                SummaryTopic(
                    title="기존 주제",
                    summary="기존 요약입니다.",
                    key_points=["기존 핵심입니다."],
                )
            ],
        )
        self.note = SummaryNote(id="note-1", text="기존 직접 요약")
        self.session = LectureSession(
            title="요약 편집 테스트",
            material=StudyMaterial(
                summary_cards=[self.card],
                summary_notes=[self.note],
            ),
        )

    def test_updates_summary_cards_and_notes_without_regeneration(self) -> None:
        repository = RecordingRepository()
        payload = SummaryBatchUpdate(
            cards=[
                {
                    "id": "card-1",
                    "topics": [
                        {
                            "title": "수정한 주제",
                            "summary": "수정한 요약입니다.",
                            "key_points": ["수정한 핵심입니다."],
                        }
                    ],
                }
            ],
            notes=[{"id": "note-1", "text": "수정한 직접 요약"}],
        )

        with (
            patch("app.main.get_session_or_404", return_value=self.session),
            patch("app.main.repository", return_value=repository),
        ):
            result = asyncio.run(update_summaries(self.session.id, payload))

        self.assertEqual(result.material.summary_cards[0].topics[0].title, "수정한 주제")
        self.assertEqual(result.material.summary_notes[0].text, "수정한 직접 요약")
        self.assertEqual(result.summary_notes_revision, 1)
        self.assertEqual(result.material.summary, "수정한 요약입니다.")
        self.assertIsNotNone(repository.saved)

    def test_adds_personal_summary_note_to_the_conversation_feed(self) -> None:
        repository = RecordingRepository()

        with (
            patch("app.main.get_session_or_404", return_value=self.session),
            patch("app.main.repository", return_value=repository),
        ):
            result = asyncio.run(
                add_summary_note(
                    self.session.id,
                    SummaryNoteCreate(text="내가 직접 추가한 요약"),
                )
            )

        self.assertEqual(result.material.summary_notes[-1].text, "내가 직접 추가한 요약")
        self.assertIsNotNone(result.material.summary_notes[-1].created_at)
        self.assertEqual(result.summary_notes_revision, 1)
        self.assertIsNotNone(repository.saved)

    def test_deletes_generated_and_personal_summaries_together(self) -> None:
        repository = RecordingRepository()
        payload = SummaryBatchUpdate(
            deleted_card_ids=["card-1"],
            deleted_note_ids=["note-1"],
        )

        with (
            patch("app.main.get_session_or_404", return_value=self.session),
            patch("app.main.repository", return_value=repository),
        ):
            result = asyncio.run(update_summaries(self.session.id, payload))

        self.assertEqual(result.material.summary_cards, [])
        self.assertEqual(result.material.summary_notes, [])
        self.assertEqual(result.summary_notes_revision, 1)
        self.assertEqual(
            result.material.summary,
            "아직 정리할 수업 내용이 없습니다. 녹음을 시작하거나 텍스트를 추가해 주세요.",
        )
        self.assertEqual(result.material.key_points, [])
        self.assertIsNotNone(repository.saved)

    def test_rejects_unknown_deleted_ids_before_changing_any_summary(self) -> None:
        repository = RecordingRepository()
        payload = SummaryBatchUpdate(
            cards=[
                {
                    "id": "card-1",
                    "topics": [
                        {
                            "title": "바뀌면 안 되는 주제",
                            "summary": "바뀌면 안 되는 요약입니다.",
                            "key_points": [],
                        }
                    ],
                }
            ],
            deleted_note_ids=["missing-note"],
        )

        with (
            patch("app.main.get_session_or_404", return_value=self.session),
            patch("app.main.repository", return_value=repository),
        ):
            with self.assertRaises(HTTPException) as context:
                asyncio.run(update_summaries(self.session.id, payload))

        self.assertEqual(context.exception.status_code, 404)
        self.assertEqual(self.session.material.summary_cards[0].topics[0].title, "기존 주제")
        self.assertIsNone(repository.saved)

    def test_rejects_unknown_ids_before_changing_any_summary(self) -> None:
        repository = RecordingRepository()
        payload = SummaryBatchUpdate(
            cards=[
                {
                    "id": "card-1",
                    "topics": [
                        {
                            "title": "바뀌면 안 되는 주제",
                            "summary": "바뀌면 안 되는 요약입니다.",
                            "key_points": [],
                        }
                    ],
                }
            ],
            notes=[{"id": "missing", "text": "없는 요약"}],
        )

        with (
            patch("app.main.get_session_or_404", return_value=self.session),
            patch("app.main.repository", return_value=repository),
        ):
            with self.assertRaises(HTTPException) as context:
                asyncio.run(update_summaries(self.session.id, payload))

        self.assertEqual(context.exception.status_code, 404)
        self.assertEqual(self.session.material.summary_cards[0].topics[0].title, "기존 주제")
        self.assertIsNone(repository.saved)


if __name__ == "__main__":
    unittest.main()
