"""Native-cache bounds and error cleanup must preserve complete PDF evidence."""
import hashlib
import json

import fitz
import pytest

from src import pdf_extractor as module


def _pdf(pages=17):
    with fitz.open() as document:
        for number in range(1, pages + 1):
            document.new_page().insert_text((72, 72), f'Original evidence page {number}: -123,456.78')
        return document.tobytes()


def _gate_is_free():
    acquired = module._PDF_PARSE_GATE.acquire(timeout=0)
    assert acquired
    module._PDF_PARSE_GATE.release()


def test_periodic_eviction_preserves_all_page_text_and_keeps_lock(monkeypatch):
    pdf = _pdf()
    with fitz.open(stream=pdf, filetype='pdf') as document:
        expected = [dict(page_number=i+1, text=page.get_text('text')) for i, page in enumerate(document)]
    calls = []
    real = fitz.TOOLS.store_shrink
    def clear(percent):
        acquired = module._PDF_PARSE_GATE.acquire(timeout=0)
        if acquired:
            module._PDF_PARSE_GATE.release()
        assert not acquired, 'native store must be cleared inside the parse lock'
        calls.append(percent)
        return real(percent)
    monkeypatch.setattr(fitz.TOOLS, 'store_shrink', clear)
    actual = module.extract_pdf_pages(pdf)
    assert hashlib.sha256(json.dumps(actual).encode()).digest() == hashlib.sha256(json.dumps(expected).encode()).digest()
    assert calls == [100, 100, 100, 100]  # start, 8, 16, final
    _gate_is_free()


def _fake(monkeypatch, *, page_error=None, close_error=None, clear_error_call=None):
    events = []
    class Page:
        def get_text(self, mode):
            events.append('text')
            if page_error is not None:
                raise page_error
            return 'complete original text'
    class Document:
        needs_pass = False
        page_count = 17
        def __iter__(self):
            return iter([Page() for _ in range(17)])
        def close(self):
            events.append('close')
            if close_error is not None:
                raise close_error
    calls = 0
    def clear(percent):
        nonlocal calls
        calls += 1
        events.append('clear')
        if calls == clear_error_call:
            raise RuntimeError('native cache cleanup failure')
    def opened(**kwargs):
        events.append('open')
        return Document()
    monkeypatch.setattr(fitz, 'open', opened)
    monkeypatch.setattr(fitz.TOOLS, 'store_shrink', clear)
    return events


@pytest.mark.parametrize('failure_at', [1, 2, 4])
def test_cleanup_failure_rejects_result_and_releases_gate(monkeypatch, failure_at):
    events = _fake(monkeypatch, clear_error_call=failure_at)
    with pytest.raises(ValueError, match='PDF缓存无法安全释放'):
        module.extract_pdf_pages(b'%PDF-local-test', wait_seconds=0)
    if failure_at == 1:
        assert 'open' not in events
    else:
        assert 'close' in events
    _gate_is_free()


def test_close_failure_still_clears_native_store_and_releases_gate(monkeypatch):
    events = _fake(monkeypatch, close_error=RuntimeError('close failed'))
    with pytest.raises(ValueError, match='PDF文档无法安全关闭'):
        module.extract_pdf_pages(b'%PDF-local-test', wait_seconds=0)
    assert events[-2:] == ['close', 'clear']
    _gate_is_free()


@pytest.mark.parametrize('primary', [MemoryError('primary allocation failure'), RuntimeError('primary text failure')])
def test_cleanup_errors_never_replace_the_original_parse_error(monkeypatch, primary):
    events = _fake(monkeypatch, page_error=primary,
                   close_error=RuntimeError('secondary close failure'), clear_error_call=2)
    expected_type = MemoryError if isinstance(primary, MemoryError) else ValueError
    with pytest.raises(expected_type) as caught:
        module.extract_pdf_pages(b'%PDF-local-test', wait_seconds=0)
    if isinstance(primary, MemoryError):
        assert caught.value is primary
    else:
        assert caught.value.__cause__ is primary
        assert '第 1 页无法安全提取文字' in str(caught.value)
    assert any('PDF资源清理也未完成' in note for note in caught.value.__notes__)
    assert events[-2:] == ['close', 'clear']
    _gate_is_free()


def test_eviction_between_real_header_and_continuation_preserves_geometry(monkeypatch):
    from pathlib import Path
    excerpt = Path(__file__).parent / 'fixtures' / 'longi_2025_signed_geometry_excerpt.pdf'
    # Place the actual table header at page 8 and its negative-sign continuation
    # at page 9: eviction must not remove provenance or alter the derived sign.
    with fitz.open() as document, fitz.open(excerpt) as source:
        for _ in range(7):
            document.new_page()
        document.insert_pdf(source)
        data = document.tobytes()
    monkeypatch.setattr(module, '_PDF_STORE_CLEAR_PAGE_INTERVAL', 10_000)
    baseline = module.extract_pdf_pages(data, include_financial_geometry=True, financial_report_year=2025)
    monkeypatch.setattr(module, '_PDF_STORE_CLEAR_PAGE_INTERVAL', 8)
    bounded = module.extract_pdf_pages(data, include_financial_geometry=True, financial_report_year=2025)
    assert bounded == baseline
    adjustment = bounded[8]['financial_geometry']['adjustments'][0]
    assert adjustment['header_page_number'] == 8 and adjustment['page_number'] == 9
    assert adjustment['original_span'] == '-\n10,205,897,803.72'
    assert adjustment['replacement_span'] == '-10,205,897,803.72'
    assert len(bounded[8]['financial_geometry']['adjustments']) == 1


@pytest.mark.parametrize('failure', ['close', 'final_store'])
def test_callers_handled_exception_cannot_hide_this_calls_cleanup_error(monkeypatch, failure):
    _fake(monkeypatch,
          close_error=RuntimeError('close failed') if failure == 'close' else None,
          clear_error_call=4 if failure == 'final_store' else None)
    handled = KeyError('already handled by caller')
    try:
        raise handled
    except KeyError as caller_error:
        with pytest.raises(ValueError, match='PDF文档无法安全关闭|PDF缓存无法安全释放'):
            module.extract_pdf_pages(b'%PDF-local-test', wait_seconds=0)
        assert caller_error is handled
        assert caller_error.args == ('already handled by caller',)
        assert not getattr(caller_error, '__notes__', [])
    _gate_is_free()
