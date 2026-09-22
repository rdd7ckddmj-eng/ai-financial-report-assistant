"""Bounded, page-level text extraction for uploaded PDF reports."""

from threading import BoundedSemaphore
from typing import TypedDict

from src.pdf_resource_policy import (
    GENERAL_OFFICIAL_PDF_MAX_BYTES,
    PDF_MAX_PAGES,
    PDF_MAX_TEXT_CHARACTERS,
    PDF_PARSE_WAIT_SECONDS,
)


_PDF_PARSE_GATE = BoundedSemaphore(value=1)


class ExtractedPage(TypedDict):
    """Text and provenance for one PDF page."""

    page_number: int
    text: str


def extract_pdf_pages(
    pdf_bytes: bytes | bytearray | memoryview,
    *,
    max_bytes: int = GENERAL_OFFICIAL_PDF_MAX_BYTES,
    max_pages: int = PDF_MAX_PAGES,
    max_text_characters: int = PDF_MAX_TEXT_CHARACTERS,
    wait_seconds: float = PDF_PARSE_WAIT_SECONDS,
) -> list[ExtractedPage]:
    """Extract complete text with provenance inside explicit safety limits.

    The function fails closed instead of returning a truncated report.  A
    process-wide gate also prevents two browser sessions from making PyMuPDF
    expand large annual reports at the same time on the free Render instance.
    """
    if not pdf_bytes:
        raise ValueError("The uploaded PDF is empty.")
    if max_bytes <= 0 or max_pages <= 0 or max_text_characters <= 0:
        raise ValueError("PDF processing limits must be greater than zero.")
    if wait_seconds < 0:
        raise ValueError("PDF wait time cannot be negative.")
    if len(pdf_bytes) > max_bytes:
        raise ValueError(
            "该 PDF 超过当前流程允许的大小上限，请改用更小的公开年报文件。"
        )

    acquired = _PDF_PARSE_GATE.acquire(timeout=wait_seconds)
    if not acquired:
        raise ValueError(
            "服务器正在解析另一份年报，请稍后再试；当前任务没有被部分处理。"
        )

    # PyMuPDF has a meaningful cold-start and memory cost.  Most visitors use
    # the company-research pages without opening a PDF, so load it only when a
    # report is actually submitted for extraction.
    document = None
    try:
        import fitz

        try:
            document = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as error:
            raise ValueError(
                "The uploaded file could not be read as a PDF."
            ) from error

        if document.needs_pass:
            raise ValueError("加密或受密码保护的 PDF 暂不支持解析。")
        if document.page_count == 0:
            raise ValueError("The uploaded PDF contains no pages.")
        if document.page_count > max_pages:
            raise ValueError(
                f"该 PDF 共 {document.page_count} 页，超过 {max_pages} 页的解析上限。"
            )

        pages: list[ExtractedPage] = []
        extracted_characters = 0
        for page_index, page in enumerate(document):
            try:
                page_text = page.get_text("text")
            except MemoryError:
                raise
            except Exception as error:
                raise ValueError(
                    "PDF 第 "
                    f"{page_index + 1} 页无法安全提取文字；"
                    "系统已停止本次解析，并且没有返回不完整证据。"
                ) from error
            extracted_characters += len(page_text)
            if extracted_characters > max_text_characters:
                raise ValueError(
                    "该 PDF 的可提取文本量超过安全上限，系统已停止并且没有返回"
                    "不完整证据。"
                )
            pages.append(
                {
                    "page_number": page_index + 1,
                    "text": page_text,
                }
            )
        return pages
    finally:
        if document is not None:
            document.close()
        _PDF_PARSE_GATE.release()
