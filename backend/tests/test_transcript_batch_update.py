import asyncio
from io import BytesIO
import unittest
from unittest.mock import patch

from fastapi import HTTPException, UploadFile

from app.main import (
    delete_reference_document,
    delete_reference_pdf,
    update_transcripts,
    upload_reference_pdfs,
)
from app.schemas import (
    LectureSession,
    ReferenceDocument,
    TranscriptBatchUpdate,
    TranscriptSegment,
)


class RecordingRepository:
    def __init__(self) -> None:
        self.saved: LectureSession | None = None

    def save(self, session: LectureSession) -> LectureSession:
        self.saved = session.model_copy(deep=True)
        return self.saved


class TranscriptBatchUpdateApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = LectureSession(
            title="일괄 편집 테스트",
            segments=[
                TranscriptSegment(id="segment-1", text="첫 번째 원문"),
                TranscriptSegment(id="segment-2", text="두 번째 원문"),
            ],
        )

    def test_batch_update_saves_all_text_without_waiting_for_summary(self) -> None:
        repository = RecordingRepository()
        payload = TranscriptBatchUpdate(
            updates=[
                {"id": "segment-1", "text": "첫 번째 수정"},
                {"id": "segment-2", "text": "두 번째 수정"},
            ],
        )

        with (
            patch("app.main.get_session_or_404", return_value=self.session),
            patch("app.main.repository", return_value=repository),
            patch("app.main.regenerate_material") as regenerate,
        ):
            result = asyncio.run(update_transcripts(self.session.id, payload))

        self.assertEqual(
            [segment.text for segment in result.segments],
            ["첫 번째 수정", "두 번째 수정"],
        )
        self.assertIsNotNone(repository.saved)
        regenerate.assert_not_called()

    def test_batch_update_rejects_unknown_segment_before_saving(self) -> None:
        repository = RecordingRepository()
        payload = TranscriptBatchUpdate(
            updates=[{"id": "missing", "text": "없는 내용"}],
        )

        with (
            patch("app.main.get_session_or_404", return_value=self.session),
            patch("app.main.repository", return_value=repository),
        ):
            with self.assertRaises(HTTPException) as context:
                asyncio.run(update_transcripts(self.session.id, payload))

        self.assertEqual(context.exception.status_code, 404)
        self.assertIsNone(repository.saved)


class ReferenceDeleteApiTests(unittest.TestCase):
    def test_delete_reference_clears_name_and_private_text_immediately(self) -> None:
        session = LectureSession(
            title="PDF 삭제 테스트",
            reference_name="wrong-document.pdf",
            reference_text="잘못 올린 참고 자료 본문",
            segments=[TranscriptSegment(id="segment-1", text="실제 수업 내용")],
        )
        repository = RecordingRepository()

        with (
            patch("app.main.get_session_or_404", return_value=session),
            patch("app.main.repository", return_value=repository),
            patch("app.main.regenerate_material") as regenerate,
        ):
            result = asyncio.run(delete_reference_pdf(session.id))

        self.assertIsNone(result.reference_name)
        self.assertIsNone(result.reference_text)
        self.assertIsNone(repository.saved.reference_name)
        self.assertIsNone(repository.saved.reference_text)
        regenerate.assert_not_called()

    def test_deletes_only_the_selected_reference(self) -> None:
        session = LectureSession(
            title="PDF 개별 삭제 테스트",
            references=[
                ReferenceDocument(id="reference-1", name="one.pdf", text="첫 번째 자료"),
                ReferenceDocument(id="reference-2", name="two.pdf", text="두 번째 자료"),
            ],
        )
        repository = RecordingRepository()

        with (
            patch("app.main.get_session_or_404", return_value=session),
            patch("app.main.repository", return_value=repository),
        ):
            result = asyncio.run(
                delete_reference_document(session.id, "reference-1")
            )

        self.assertEqual(
            [reference.name for reference in result.references],
            ["two.pdf"],
        )
        self.assertNotIn("첫 번째", result.reference_text)
        self.assertIn("두 번째", result.reference_text)


class ReferenceUploadApiTests(unittest.TestCase):
    def test_uploads_multiple_references_in_one_request(self) -> None:
        session = LectureSession(title="PDF 복수 업로드 테스트")
        repository = RecordingRepository()
        documents = [
            UploadFile(file=BytesIO(b"first"), filename="one.pdf"),
            UploadFile(file=BytesIO(b"second"), filename="two.pdf"),
        ]

        with (
            patch("app.main.get_session_or_404", return_value=session),
            patch("app.main.repository", return_value=repository),
            patch(
                "app.main.extract_pdf_text",
                side_effect=["첫 번째 PDF 본문", "두 번째 PDF 본문"],
            ),
        ):
            result = asyncio.run(upload_reference_pdfs(session.id, documents))

        self.assertEqual(
            [reference.name for reference in result.references],
            ["one.pdf", "two.pdf"],
        )
        self.assertIn("첫 번째 PDF 본문", result.reference_text)
        self.assertIn("두 번째 PDF 본문", result.reference_text)
        self.assertIsNotNone(repository.saved)


if __name__ == "__main__":
    unittest.main()
