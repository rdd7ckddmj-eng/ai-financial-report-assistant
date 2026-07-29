"""Page-level text extraction for uploaded PDF reports."""

from typing import TypedDict

import fitz


class ExtractedPage(TypedDict):
    """Text and provenance for one PDF page."""

    page_number: int
    text: str


def extract_pdf_pages(pdf_bytes: bytes) -> list[ExtractedPage]:
    """Extract text from a PDF while preserving one-based page numbers."""
    if not pdf_bytes:
        raise ValueError("The uploaded PDF is empty.")

    try:
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as error:
        raise ValueError("The uploaded file could not be read as a PDF.") from error

    try:
        if document.page_count == 0:
            raise ValueError("The uploaded PDF contains no pages.")

        pages: list[ExtractedPage] = []
        for page_index, page in enumerate(document):
            pages.append(
                {
                    "page_number": page_index + 1,
                    "text": page.get_text("text"),
                }
            )
        return pages
    finally:
        document.close()
