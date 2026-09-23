"""Real PDF glyph geometry plus synthetic adversarial table layouts."""
import hashlib
import json
from pathlib import Path

import pymupdf
import pytest

from src.pdf_signed_amount_geometry import (
    MAX_DRAWINGS, MAX_DRAWING_ITEMS, MAX_PAGE_TEXT, MAX_WORDS,
    derive_signed_amount_geometry,
)


def _number(page, right, baseline, text):
    width = pymupdf.get_text_length(text, fontname='helv', fontsize=10)
    page.insert_text((right-width, baseline), text, fontname='helv', fontsize=10)


def _synthetic(kind='valid'):
    document = pymupdf.open()
    page = document.new_page(width=650, height=400)
    title = '母公司利润表' if kind == 'parent' else '合并利润表'
    page.insert_text((250, 75), title, fontname='china-s', fontsize=10)
    columns, rows = [40, 300, 345, 445, 555], [100, 130, 155, 190, 215]
    for x in columns:
        if kind == 'missing_border' and x == 445:
            continue
        page.draw_line((x, 100), (x, 215), width=.5)
    for y in rows:
        page.draw_line((40, y), (555, y), width=.5)
    page.insert_text((45, 118), '项目', fontname='china-s', fontsize=10)
    page.insert_text((305, 118), '附注', fontname='china-s', fontsize=10)
    years = (2024, 2025) if kind == 'reversed_years' else (2025, 2024)
    for left, year in zip((370, 470), years):
        page.insert_text((left, 118), str(year), fontname='helv', fontsize=10)
        page.insert_text((left+25, 118), '年度', fontname='china-s', fontsize=10)
    if kind == 'extra_year':
        page.insert_text((310, 118), '2023', fontname='helv', fontsize=10)
    page.insert_text((45, 147), '减：营业外支出', fontname='china-s', fontsize=10)
    _number(page, 440, 147, '3.00')
    _number(page, 550, 147, '4.00')
    label = '四、营业利润' if kind == 'unknown_label' else '四、利润总额'
    page.insert_text((45, 175), label, fontname='china-s', fontsize=10)
    if kind == 'current_column':
        _number(page, 440, 168.5, '-')
        _number(page, 440, 180.5, '678.90')
        _number(page, 550, 174.5, '-123.45')
    elif kind == 'bare_hyphen_empty_cell':
        # Text extraction places a missing current cell immediately before the
        # previous-year amount; the two are NOT one negative number.
        _number(page, 440, 174.5, '-')
        _number(page, 550, 174.5, '678.90')
    else:
        _number(page, 440, 174.5, '-123.45')
        sign_right = 470 if kind == 'left_aligned' else (635 if kind == 'outside_table' else 550)
        _number(page, sign_right, 168.5, '-')
        if kind != 'isolated_sign':
            amount_right = 440 if kind == 'cross_column' else (635 if kind == 'outside_table' else 550)
            baseline = 202.5 if kind == 'cross_row' else (168.5 if kind == 'same_baseline' else 180.5)
            _number(page, amount_right, baseline, '678.90')
        if kind == 'duplicate_candidate':
            _number(page, 550, 185, '999.99')
    next_label = '减：其他费用' if kind == 'wrong_next_label' else '减：所得税费用'
    page.insert_text((45, 205), next_label, fontname='china-s', fontsize=10)
    _number(page, 440, 205, '-1.00')
    _number(page, 550, 205, '-2.00')
    return document


@pytest.mark.parametrize('kind,column_year', [('valid', 2024), ('current_column', 2025)])
def test_synthetic_geometry_repairs_one_known_sign_without_changing_original(kind, column_year):
    with _synthetic(kind) as document:
        page = document[0]
        original = page.get_text()
        result = derive_signed_amount_geometry(page, original_text=original, report_year=2025)
        assert len(result['adjustments']) == 1
        correction = result['adjustments'][0]
        assert correction['original_span'] == '-\n678.90'
        assert correction['replacement_span'] == '-678.90'
        assert correction['column_year'] == column_year
        assert original[correction['start_offset']:correction['end_offset']] == correction['original_span']
        assert result['parser_text'] == (original[:correction['start_offset']] + '-678.90'
                                         + original[correction['end_offset']:])
        assert page.get_text() == original


@pytest.mark.parametrize('kind', [
    'bare_hyphen_empty_cell', 'cross_column', 'cross_row', 'isolated_sign',
    'duplicate_candidate', 'unknown_label', 'outside_table', 'missing_border',
    'reversed_years', 'extra_year', 'parent', 'wrong_next_label', 'left_aligned',
    'same_baseline',
])
def test_ambiguous_or_unrelated_glyphs_preserve_original_text(kind):
    with _synthetic(kind) as document:
        page = document[0]
        original = page.get_text()
        result = derive_signed_amount_geometry(page, original_text=original, report_year=2025)
        assert result['adjustments'] == []
        assert result['parser_text'] == original


def test_original_text_mismatch_and_wrong_year_cannot_produce_adjustment():
    with _synthetic() as document:
        page = document[0]
        for original, year in [(page.get_text() + 'injected text', 2025), (page.get_text(), 2024)]:
            result = derive_signed_amount_geometry(page, original_text=original, report_year=year)
            assert result['adjustments'] == []
            assert result['parser_text'] == original


@pytest.mark.parametrize('heading', [
    '母公司利润表（续）', '2、母 公 司 利 润 表', '合并现金流量表',
    '（二）母公司利润表', '(二)母公司利润表', '二 母公司利润表',
    '二母公司利润表', '(2) 母 公 司 利 润 表 （续）',
])
def test_a_later_statement_heading_blocks_reusing_the_earlier_group_header(heading):
    with _synthetic() as document:
        continuation = pymupdf.open()
        continuation.insert_pdf(document)
        continuation.insert_pdf(document)
        try:
            current = continuation[1]
            current.add_redact_annot(pymupdf.Rect(245, 60, 310, 82))
            current.apply_redactions()
            baseline = derive_signed_amount_geometry(current, previous_page=continuation[0], original_text=current.get_text())
            assert len(baseline['adjustments']) == 1
            continuation[0].insert_text((200, 270), heading, fontname='china-s', fontsize=10)
            result = derive_signed_amount_geometry(current, previous_page=continuation[0], original_text=current.get_text())
            assert result['adjustments'] == []
        finally:
            continuation.close()


def test_real_longi_pdf_excerpt_uses_adjacent_header_and_cell_geometry():
    path = Path(__file__).parent / 'fixtures' / 'longi_2025_signed_geometry_excerpt.pdf'
    metadata = json.loads(path.with_suffix('.json').read_text())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == metadata['excerpt_sha256']
    assert metadata['page_mapping'] == {'1': 125, '2': 126}
    with pymupdf.open(path) as document:
        page, previous = document[1], document[0]
        original = page.get_text()
        result = derive_signed_amount_geometry(page, previous_page=previous, original_text=original, report_year=2025)
        assert len(result['adjustments']) == 1
        correction = result['adjustments'][0]
        assert correction['original_span'] == '-\n10,205,897,803.72'
        assert correction['replacement_span'] == '-10,205,897,803.72'
        assert correction['start_offset'] == 377 and correction['end_offset'] == 396
        assert correction['page_number'] == 2 and correction['header_page_number'] == 1
        assert correction['header_years'] == [2025, 2024] and correction['column_year'] == 2024
        cell = correction['cell_bbox']
        for box in (correction['sign_bbox'], correction['amount_bbox']):
            assert cell[0] <= box[0] < box[2] <= cell[2]
            assert cell[1] <= box[1] < box[3] <= cell[3]
        assert page.get_text() == original
        assert derive_signed_amount_geometry(page, original_text=original)['adjustments'] == []
        assert derive_signed_amount_geometry(page, previous_page=page)['adjustments'] == []


class _PageProxy:
    def __init__(self, page, mode):
        self.page, self.mode, self.calls = page, mode, []

    def __getattr__(self, name):
        return getattr(self.page, name)

    def get_text(self, kind='text'):
        self.calls.append(kind)
        if kind == 'words' and self.mode == 'word_budget':
            return self.page.get_text(kind) * MAX_WORDS
        return self.page.get_text(kind)

    def get_drawings(self):
        self.calls.append('drawings')
        if self.mode == 'drawing_budget':
            return [{'items': []}] * (MAX_DRAWINGS + 1)
        if self.mode == 'item_budget':
            return [{'items': [('unsupported',)] * (MAX_DRAWING_ITEMS + 1)}]
        return self.page.get_drawings()


@pytest.mark.parametrize('mode', ['word_budget', 'drawing_budget', 'item_budget'])
def test_geometry_budgets_stop_without_any_correction(mode):
    with _synthetic() as document:
        page = _PageProxy(document[0], mode)
        original = page.get_text()
        result = derive_signed_amount_geometry(page, original_text=original)
        assert result['adjustments'] == [] and result['parser_text'] == original


def test_irrelevant_or_overlong_text_never_requests_geometry():
    with _synthetic() as document:
        for text in ['普通页面没有拆行负号', 'x' * (MAX_PAGE_TEXT + 1)]:
            page = _PageProxy(document[0], 'normal')
            result = derive_signed_amount_geometry(page, original_text=text)
            assert result['adjustments'] == []
            assert 'words' not in page.calls and 'drawings' not in page.calls


@pytest.mark.parametrize('kind', ['valid', 'current_column'])
def test_producer_and_consumer_agree_on_plain_decimal_amounts(kind):
    from src.pdf_extractor import extract_pdf_pages
    from src.pdf_text_derivation import replay_financial_geometry
    with _synthetic(kind) as document:
        data = document.tobytes()
    original = extract_pdf_pages(data)
    enhanced = extract_pdf_pages(data, include_financial_geometry=True, financial_report_year=2025)
    assert original[0]['text'] == enhanced[0]['text']
    parsed, adjustments = replay_financial_geometry(enhanced[0],
        pdf_fingerprint=hashlib.sha256(data).hexdigest(), report_year=2025)
    assert len(adjustments) == 1
    assert adjustments[0]['replacement_span'] == '-678.90'
    assert parsed == enhanced[0]['financial_geometry']['parser_text']
