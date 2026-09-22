import fitz
import pytest

from src import pdf_extractor
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


def test_extract_pdf_pages_rejects_oversized_input_before_opening() -> None:
    with pytest.raises(ValueError, match="超过当前流程允许的大小上限"):
        extract_pdf_pages(b"%PDF-oversized", max_bytes=4)


def test_extract_pdf_pages_rejects_excess_page_count() -> None:
    with pytest.raises(ValueError, match="超过 1 页"):
        extract_pdf_pages(make_two_page_pdf(), max_pages=1)


def test_extract_pdf_pages_rejects_excess_text_without_partial_result() -> None:
    with pytest.raises(ValueError, match="可提取文本量超过安全上限"):
        extract_pdf_pages(make_two_page_pdf(), max_text_characters=10)


def test_extract_pdf_pages_rejects_password_protected_pdf() -> None:
    document = fitz.open()
    document.new_page().insert_text((72, 72), "Protected evidence")
    protected_bytes = document.tobytes(
        encryption=fitz.PDF_ENCRYPT_AES_256,
        owner_pw="owner-password",
        user_pw="reader-password",
    )
    document.close()

    with pytest.raises(ValueError, match="受密码保护"):
        extract_pdf_pages(protected_bytes)


def test_extract_pdf_pages_releases_gate_after_parse_failure() -> None:
    with pytest.raises(ValueError, match="could not be read as a PDF"):
        extract_pdf_pages(b"not-a-pdf")

    pages = extract_pdf_pages(make_two_page_pdf(), wait_seconds=0)

    assert len(pages) == 2


def test_extract_pdf_pages_fails_fast_when_another_parse_is_running() -> None:
    assert pdf_extractor._PDF_PARSE_GATE.acquire(timeout=0)
    try:
        with pytest.raises(ValueError, match="正在解析另一份年报"):
            extract_pdf_pages(make_two_page_pdf(), wait_seconds=0)
    finally:
        pdf_extractor._PDF_PARSE_GATE.release()


def test_page_runtime_error_is_normalised_and_gate_released(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A third-party page failure must not expose a traceback or hold the gate."""
    pdf_bytes = make_two_page_pdf()
    original_open = fitz.open

    class FailingPage:
        def get_text(self, _mode: str) -> str:
            raise RuntimeError("third-party parser failed")

    class FailingDocument:
        needs_pass = False
        page_count = 1

        def __iter__(self):
            return iter([FailingPage()])

        def close(self) -> None:
            return None

    monkeypatch.setattr(fitz, "open", lambda **_kwargs: FailingDocument())
    with pytest.raises(ValueError, match="第 1 页无法安全提取文字"):
        extract_pdf_pages(pdf_bytes, wait_seconds=0)

    monkeypatch.setattr(fitz, "open", original_open)
    assert len(extract_pdf_pages(pdf_bytes, wait_seconds=0)) == 2
