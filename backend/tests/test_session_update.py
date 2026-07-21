import unittest

from pydantic import ValidationError

from app.schemas import SessionUpdate, TranscriptUpdate


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


if __name__ == "__main__":
    unittest.main()
