import unittest

from pydantic import ValidationError

from app.schemas import (
    SessionUpdate,
    SummaryBatchUpdate,
    SummaryNoteCreate,
    TranscriptBatchUpdate,
    TranscriptUpdate,
)


class SessionUpdateTests(unittest.TestCase):
    def test_title_is_trimmed(self) -> None:
        payload = SessionUpdate(title="  수정한 수업 제목  ")
        self.assertEqual(payload.title, "수정한 수업 제목")

    def test_blank_title_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            SessionUpdate(title="   ")

    def test_category_can_be_changed_or_cleared_without_a_title(self) -> None:
        self.assertEqual(SessionUpdate(category_id="category-1").category_id, "category-1")
        self.assertIsNone(SessionUpdate(category_id=None).category_id)

    def test_empty_session_update_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            SessionUpdate()

    def test_sort_order_can_be_updated_without_other_fields(self) -> None:
        self.assertEqual(SessionUpdate(sort_order=-1.5).sort_order, -1.5)

    def test_null_sort_order_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            SessionUpdate(sort_order=None)

    def test_lesson_text_is_trimmed(self) -> None:
        payload = TranscriptUpdate(text="  수정한 수업 내용  ")
        self.assertEqual(payload.text, "수정한 수업 내용")

    def test_blank_lesson_text_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            TranscriptUpdate(text="   ")

    def test_summary_note_is_trimmed(self) -> None:
        payload = SummaryNoteCreate(text="  내가 적은 필기  ")
        self.assertEqual(payload.text, "내가 적은 필기")

    def test_blank_summary_note_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            SummaryNoteCreate(text="   ")

    def test_batch_lesson_text_is_trimmed(self) -> None:
        payload = TranscriptBatchUpdate(
            updates=[{"id": "segment-1", "text": "  한 번에 수정한 내용  "}],
        )
        self.assertEqual(payload.updates[0].text, "한 번에 수정한 내용")

    def test_batch_rejects_duplicate_segment_ids(self) -> None:
        with self.assertRaises(ValidationError):
            TranscriptBatchUpdate(
                updates=[
                    {"id": "segment-1", "text": "첫 번째 내용"},
                    {"id": "segment-1", "text": "두 번째 내용"},
                ],
            )

    def test_summary_batch_trims_topics_notes_and_key_points(self) -> None:
        payload = SummaryBatchUpdate(
            cards=[
                {
                    "id": "card-1",
                    "topics": [
                        {
                            "title": "  REST API  ",
                            "summary": "  요청과 응답을 설명합니다.  ",
                            "key_points": ["  HTTP를 사용합니다.  ", "   "],
                        }
                    ],
                }
            ],
            notes=[{"id": "note-1", "text": "  직접 정리한 요약  "}],
        )

        self.assertEqual(payload.cards[0].topics[0].title, "REST API")
        self.assertEqual(payload.cards[0].topics[0].key_points, ["HTTP를 사용합니다."])
        self.assertEqual(payload.notes[0].text, "직접 정리한 요약")

    def test_summary_batch_requires_at_least_one_update(self) -> None:
        with self.assertRaises(ValidationError):
            SummaryBatchUpdate()


if __name__ == "__main__":
    unittest.main()
