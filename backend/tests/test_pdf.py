import unittest
from unittest.mock import patch

from app.services.pdf import extract_pdf_text


class PdfExtractionTests(unittest.TestCase):
    def test_extracts_text_with_page_labels(self) -> None:
        class Page:
            def __init__(self, text: str) -> None:
                self.text = text

            def extract_text(self) -> str:
                return self.text

        class Reader:
            is_encrypted = False
            pages = [Page("train set 과 test set"), Page("평가 데이터 설명")]

        with patch("app.services.pdf.PdfReader", return_value=Reader()):
            text = extract_pdf_text(b"pdf")

        self.assertIn("[PDF 1페이지]", text)
        self.assertIn("train set", text)
        self.assertIn("[PDF 2페이지]", text)

    def test_rejects_pdf_without_extractable_text(self) -> None:
        class EmptyPage:
            def extract_text(self) -> str:
                return ""

        class Reader:
            is_encrypted = False
            pages = [EmptyPage()]

        with patch("app.services.pdf.PdfReader", return_value=Reader()):
            with self.assertRaisesRegex(ValueError, "텍스트를 찾지 못했습니다"):
                extract_pdf_text(b"pdf")


if __name__ == "__main__":
    unittest.main()
