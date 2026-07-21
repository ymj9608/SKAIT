import unittest

from pydantic import ValidationError

from app.schemas import SessionUpdate, SummaryNoteCreate, TranscriptUpdate


class SessionUpdateTests(unittest.TestCase):
    def test_title_is_trimmed(self) -> None:
        payload = SessionUpdate(title="  수정한 수업 제목  ")
        self.assertEqual(payload.title, "수정한 수업 제목")

    def test_blank_title_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            SessionUpdate(title="   ")

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


if __name__ == "__main__":
    unittest.main()
