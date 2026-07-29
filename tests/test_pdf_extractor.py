import fitz
import pytest

from src.pdf_extractor import extract_pdf_pages


def make_two_page_pdf() -> bytes:
    document = fitz.open()
    first_page = document.new_page()
    first_page.insert_text((72, 72), "Revenue was GBP 1.2 million.")
    second_page = document.new_page()
    second_page.insert_text((72, 72), "Net profit was GBP 120,000.")
    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


def test_extract_pdf_pages_preserves_text_and_page_numbers() -> None:
    pages = extract_pdf_pages(make_two_page_pdf())

    assert [page["page_number"] for page in pages] == [1, 2]
    assert "Revenue was GBP 1.2 million." in pages[0]["text"]
    assert "Net profit was GBP 120,000." in pages[1]["text"]


def test_extract_pdf_pages_rejects_empty_file() -> None:
    with pytest.raises(ValueError, match="uploaded PDF is empty"):
        extract_pdf_pages(b"")


def test_extract_pdf_pages_rejects_invalid_pdf() -> None:
    with pytest.raises(ValueError, match="could not be read as a PDF"):
        extract_pdf_pages(b"This is not a PDF.")
