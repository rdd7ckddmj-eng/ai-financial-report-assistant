"""Blank cash-flow cells cannot borrow a following account's amounts."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from src.cash_flow_extractor import (
    CHINESE_CASH_FLOW_LABELS,
    _bounded_cash_flow_text,
    _extract_chinese_row_pair,
    _normalise_lines,
    extract_cash_flow_figures,
    find_cash_flow_figures,
)


FIXTURE = json.loads((Path(__file__).parent / 'fixtures/gujing_cash_flow_blank_exchange_2025.json').read_text())
NOTE_REPORTS = json.loads((Path(__file__).parent / 'fixtures/cash_flow_known_note_headers_2025.json').read_text())['reports']


@pytest.mark.parametrize('key', CHINESE_CASH_FLOW_LABELS)
@pytest.mark.parametrize('header', ['', '项目\n2025年度\n2024年度\n', '项目\n附注\n2025年度\n2024年度\n'])
@pytest.mark.parametrize('boundary', ['五、现金及现金等价物净增加额', '其他现金流量科目', '母公司现金流量表'])
def test_empty_row_stops_at_next_account_with_or_without_note_header(key, header, boundary):
    # Deliberately use an unrelated label if the tested row itself is net change.
    if key == 'net_change' and boundary == '五、现金及现金等价物净增加额':
        boundary = '加：期初现金及现金等价物余额'
    lines = _normalise_lines('合并现金流量表\n' + header + CHINESE_CASH_FLOW_LABELS[key][0]
                             + '\n\n' + boundary + '\n100.00\n80.00')
    assert _extract_chinese_row_pair(lines, CHINESE_CASH_FLOW_LABELS[key]) is None


@pytest.mark.parametrize('columns', [2, 4])
@pytest.mark.parametrize('between', ['无数据', '不适用', 'NaN', '七79', '（净减少以“-”号填列）'])
def test_no_note_header_does_not_authorize_skipping_text_to_later_amounts(columns, between):
    title = '合并现金流量表' if columns == 2 else '合并及公司现金流量表'
    lines = _normalise_lines(title + '\n汇率变动对现金及现金等价物的影响\n'
                             + between + '\n100\n80' + ('\n50\n40' if columns == 4 else ''))
    assert _extract_chinese_row_pair(lines, CHINESE_CASH_FLOW_LABELS['exchange'],
                                     value_column_count=columns) is None


def test_balanced_zero_movement_cannot_make_missing_exchange_evidence_pass():
    # Before the fix, the empty exchange row stole the next row's explicit
    # zeros and the entire synthetic statement incorrectly reconciled.
    text = '''合并现金流量表
单位：元
项目 2025年度 2024年度
经营活动产生的现金流量净额 100 80
投资活动产生的现金流量净额 -40 -30
筹资活动产生的现金流量净额 -60 -50
四、汇率变动对现金及现金等价物的影响

五、现金及现金等价物净增加额
0
0
加：期初现金及现金等价物余额 200 200
六、期末现金及现金等价物余额 200 200
'''
    assert extract_cash_flow_figures(1, text) is None
    explicit = text.replace('的影响\n\n', '的影响\n0\n0\n')
    assert extract_cash_flow_figures(1, explicit) is not None


@pytest.mark.parametrize('amounts', ['0\n0', '-\n—', '100.00\n80.00'])
def test_explicit_cells_are_preserved_without_inventing_blank_values(amounts):
    lines = _normalise_lines('合并现金流量表\n汇率变动对现金及现金等价物的影响\n'
                             + amounts + '\n其他现金流量科目\n1000\n800')
    expected = (100.0, 80.0) if amounts.startswith('100') else (0.0, 0.0)
    assert _extract_chinese_row_pair(lines, CHINESE_CASH_FLOW_LABELS['exchange']) == expected


@pytest.mark.parametrize('note,accepted', [
    ('(五)60(1)', True), ('（五）60（1）', True),
    ('(五)60(1)其他科目', False), ('(五)60(1)\n其他科目', False),
    ('(五)60(1)\n(五)60(2)', False), ('(五)60(1)\n母公司现金流量表', False),
])
def test_existing_named_period_note_column_only_skips_one_complete_note_cell(note, accepted):
    lines = _normalise_lines('合并现金流量表\n项目\n附注\n本年发生额\n上年发生额\n'
        '一、经营活动产生的现金流量：\n经营活动产生的现金流量净额\n'
        + note + '\n100.00\n80.00')
    pair = _extract_chinese_row_pair(lines, CHINESE_CASH_FLOW_LABELS['operating'])
    assert pair == ((100.0, 80.0) if accepted else None)


@pytest.mark.parametrize('header', [
    '项目\n本年发生额\n上年发生额', '项目\n附注\n上年发生额\n本年发生额',
    '项目\n附注\n本年发生额\n上年发生额\n更早年度',
])
def test_parenthesized_chinese_note_requires_exact_ordered_two_period_note_header(header):
    lines = _normalise_lines('合并现金流量表\n' + header
        + '\n一、经营活动产生的现金流量：\n经营活动产生的现金流量净额\n(五)60(1)\n100.00\n80.00')
    assert _extract_chinese_row_pair(lines, CHINESE_CASH_FLOW_LABELS['operating']) is None


def test_real_gujing_blank_exchange_stays_missing_and_does_not_borrow_net_change_or_parent():
    untouched = deepcopy(FIXTURE)
    pages = [(p['page_number'], p['text']) for p in FIXTURE['pages']]
    assert [p for p, _ in pages] == [64, 65, 66]
    assert '单位：元' in pages[0][1] and '2025 年度' in pages[0][1] and '2024 年度' in pages[0][1]
    lines = _normalise_lines(_bounded_cash_flow_text('\n'.join(t for _, t in pages)))
    assert _extract_chinese_row_pair(lines, CHINESE_CASH_FLOW_LABELS['exchange']) is None
    assert _extract_chinese_row_pair(lines, CHINESE_CASH_FLOW_LABELS['net_change']) == (-2698882875.62, 516967276.83)
    assert _extract_chinese_row_pair(lines, CHINESE_CASH_FLOW_LABELS['operating']) == (1947212977.0, 4727652873.85)
    assert find_cash_flow_figures(pages) is None
    assert FIXTURE == untouched


@pytest.mark.parametrize('boundary', ['下一科目', '母公司现金流量表'])
def test_missing_pair_cannot_be_repaired_across_a_page_boundary(boundary):
    pages = [(8, '合并现金流量表\n单位：元\n汇率变动对现金及现金等价物的影响\n'),
             (9, boundary + '\n100\n80')]
    assert extract_cash_flow_figures(8, '\n'.join(t for _, t in pages), source_pages=pages) is None


@pytest.mark.parametrize('report', NOTE_REPORTS, ids=lambda report: report['code'])
def test_real_note_headers_keep_original_group_amounts_without_changing_pdf_text(report):
    original = deepcopy(report)
    result = find_cash_flow_figures([(p['page_number'], p['text']) for p in report['pages']])
    assert result is not None
    for key, expected in report['expected_figures'].items():
        assert result[key] == expected
    assert report == original


NOTES = {'000333.SZ': '四(64)(h)', '601088.SH': '五、47(1)',
         '601766.SH': '七、70', '600941.SH': '四(55)(a)', '600600.SH': '(五)57(1)'}


def _change_note_report(code, old, new):
    report = deepcopy(next(r for r in NOTE_REPORTS if r['code'] == code))
    for page in report['pages']:
        if old in page['text']:
            page['text'] = page['text'].replace(old, new, 1)
            return [(p['page_number'], p['text']) for p in report['pages']]
    raise AssertionError('Counterexample must change a real observed source string')


@pytest.mark.parametrize('code', NOTES)
@pytest.mark.parametrize('damage', ['unknown_before', 'unknown_after', 'extra_note', 'wrong_note', 'extra_cell', 'invalid_cell'])
def test_explicit_note_header_never_skips_unknown_text_or_extra_cells(code, damage):
    note = NOTES[code]
    changed = {'unknown_before': '其他科目\n' + note,
               'unknown_after': note + '\n其他科目',
               'extra_note': note + '\n' + note,
               'wrong_note': note + '其他科目',
               'extra_cell': note + '\n17',
               'invalid_cell': note + '\n17.2.3'}[damage]
    assert find_cash_flow_figures(_change_note_report(code, note, changed)) is None


@pytest.mark.parametrize('code', NOTES)
def test_compatibility_notes_require_the_explicit_note_column(code):
    assert find_cash_flow_figures(_change_note_report(code, '附注', '未注明')) is None


@pytest.mark.parametrize('code', ['000333.SZ', '600600.SH'])
def test_four_column_note_header_cannot_reverse_group_and_parent_roles(code):
    assert find_cash_flow_figures(_change_note_report(code, '合并 \n', '公司 \n')) is None
