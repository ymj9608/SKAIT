from io import BytesIO

from pypdf import PdfReader


def extract_pdf_text(raw: bytes, max_pages: int = 200, max_chars: int = 500_000) -> str:
    """텍스트 기반 PDF에서 페이지 순서를 유지한 참고 자료를 추출합니다."""
    try:
        reader = PdfReader(BytesIO(raw))
    except Exception as exc:
        raise ValueError("PDF 파일을 읽을 수 없습니다.") from exc

    if reader.is_encrypted:
        try:
            unlocked = reader.decrypt("")
        except Exception as exc:
            raise ValueError("암호화된 PDF는 사용할 수 없습니다.") from exc
        if not unlocked:
            raise ValueError("암호화된 PDF는 사용할 수 없습니다.")

    pages: list[str] = []
    total_chars = 0
    for page_number, page in enumerate(reader.pages[:max_pages], start=1):
        try:
            text = " ".join((page.extract_text() or "").replace("\x00", " ").split())
        except Exception:
            text = ""
        if not text:
            continue
        remaining = max_chars - total_chars
        if remaining <= 0:
            break
        page_text = text[:remaining]
        pages.append(f"[PDF {page_number}페이지] {page_text}")
        total_chars += len(page_text)

    extracted = "\n".join(pages).strip()
    if not extracted:
        raise ValueError(
            "PDF에서 텍스트를 찾지 못했습니다. 스캔 이미지 PDF는 텍스트 PDF로 변환해 주세요."
        )
    return extracted
