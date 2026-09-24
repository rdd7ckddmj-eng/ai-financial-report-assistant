"""Bounded, page-level text extraction for uploaded PDF reports."""

from threading import BoundedSemaphore
from typing import TypedDict, NotRequired
from hashlib import sha256

from src.pdf_resource_policy import (
    GENERAL_OFFICIAL_PDF_MAX_BYTES,
    PDF_MAX_PAGES,
    PDF_MAX_TEXT_CHARACTERS,
    PDF_PARSE_WAIT_SECONDS,
)


_PDF_PARSE_GATE = BoundedSemaphore(value=1)
# MuPDF's native resource store can reach 256 MiB inside one full report.
# Closing the document later does not necessarily return that allocator high
# water mark to the OS. Keep reusable native resources bounded during parsing.
_PDF_STORE_CLEAR_PAGE_INTERVAL = 8


def _clear_pdf_store(module) -> None:
    try:
        module.TOOLS.store_shrink(100)
    except MemoryError:
        raise
    except Exception as error:
        raise ValueError("PDF缓存无法安全释放，本次解析已停止。") from error


class ExtractedPage(TypedDict):
    """Text and provenance for one PDF page."""

    page_number: int
    text: str
    financial_geometry: NotRequired[dict]
    native_text_recovery: NotRequired[dict]


def extract_pdf_pages(
    pdf_bytes: bytes | bytearray | memoryview,
    *,
    max_bytes: int = GENERAL_OFFICIAL_PDF_MAX_BYTES,
    max_pages: int = PDF_MAX_PAGES,
    max_text_characters: int = PDF_MAX_TEXT_CHARACTERS,
    wait_seconds: float = PDF_PARSE_WAIT_SECONDS,
    include_financial_geometry: bool = False,
    financial_report_year: int | None = None,
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
    if type(include_financial_geometry) is not bool or (financial_report_year is not None
            and (type(financial_report_year) is not int or not 1990 <= financial_report_year <= 2200)):
        raise ValueError("财务版面解析选项或年度无效。")
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
    fitz = None
    original_error = None
    try:
        import fitz

        _clear_pdf_store(fitz)
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
        adjustment_count = 0
        native_recoveries = []
        fingerprint = sha256(pdf_bytes).hexdigest() if include_financial_geometry else None
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
            if include_financial_geometry:
                from src.pdf_actualtext_recovery import (
                    derive_native_text_recovery, validate_native_text_recoveries,
                )
                try:
                    native = derive_native_text_recovery(document, page,
                        original_text=page_text, report_year=financial_report_year,
                        pdf_fingerprint=fingerprint, module=fitz)
                except MemoryError:
                    raise
                except Exception as error:
                    raise ValueError(f'PDF 第 {page_index + 1} 页原生文字依据无法安全检查。') from error
                if native is not None:
                    native_recoveries.append(native)
                    validate_native_text_recoveries(native_recoveries,
                        pdf_fingerprint=fingerprint, report_year=financial_report_year)
                    extracted_characters += len(native['native_text'])
                    if extracted_characters > max_text_characters:
                        raise ValueError('PDF原生文字恢复超过安全文本上限，未返回部分证据。')
                    pages[-1]['native_text_recovery'] = native
                from src.pdf_signed_amount_geometry import derive_signed_amount_geometry
                from src.pdf_text_derivation import MAX_DOCUMENT_ADJUSTMENTS
                try:
                    # Both derivations must never silently compose. Native
                    # recovery is already a complete, explicitly sourced page.
                    derivation = {'adjustments': []} if native is not None else derive_signed_amount_geometry(
                        page, report_year=financial_report_year, original_text=page_text,
                        previous_page=document[page_index - 1] if page_index else None)
                except MemoryError:
                    raise
                except Exception as error:
                    raise ValueError(f'PDF 第 {page_index + 1} 页无法完成版面检查，已停止本次解析。') from error
                if derivation['adjustments']:
                    adjustment_count += len(derivation['adjustments'])
                    extracted_characters += len(derivation['parser_text'])
                    if adjustment_count > MAX_DOCUMENT_ADJUSTMENTS or extracted_characters > max_text_characters:
                        raise ValueError("PDF版面处理超过本次安全上限，没有返回不完整证据。")
                    pages[-1]['financial_geometry'] = dict(derivation, document_sha256=fingerprint,
                        original_text_sha256=sha256(page_text.encode()).hexdigest())
            if (page_index + 1) % _PDF_STORE_CLEAR_PAGE_INTERVAL == 0:
                # Only evicts regenerable library resources: all original text
                # and any audited geometry records above remain unchanged.
                _clear_pdf_store(fitz)
        return pages
    except BaseException as error:
        # Capture only this invocation's failure. sys.exc_info() inside finally
        # could instead expose an already-handled exception in the caller.
        original_error = error
        raise
    finally:
        cleanup_error = None
        try:
            if document is not None:
                try:
                    document.close()
                except MemoryError as error:
                    cleanup_error = error
                except Exception as error:
                    cleanup_error = ValueError("PDF文档无法安全关闭，本次解析已停止。")
                    cleanup_error.__cause__ = error
                except BaseException as error:
                    cleanup_error = error
        finally:
            try:
                if fitz is not None:
                    try:
                        _clear_pdf_store(fitz)
                    except BaseException as error:
                        if cleanup_error is None:
                            cleanup_error = error
                        else:
                            cleanup_error.add_note(f"另有PDF缓存清理错误：{error}")
            finally:
                # A close/cleanup failure must never strand the process-wide
                # gate and prevent all subsequent visitors from parsing.
                _PDF_PARSE_GATE.release()
        if cleanup_error is not None:
            if original_error is not None:
                original_error.add_note(f"PDF资源清理也未完成：{cleanup_error}")
            else:
                raise cleanup_error
