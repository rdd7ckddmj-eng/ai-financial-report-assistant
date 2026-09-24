"""Full source windows: annual periods, split pretax labels and blank cells."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from src.financial_statement_extractor import find_income_statement_figures
from src.general_income_reconciliation import check_general_income_reconciliation
from src.income_row_layout_recovery import recover_cross_page_profit_before_tax

SAMPLES = {s['code']: s for s in json.loads(
    (Path(__file__).parent / 'fixtures/coverage14_income_boundaries.json').read_text())}


def pages(code):
    return [(p['page_number'], p['text']) for p in SAMPLES[code]['pages']]


def changed(code, page_number, old, new):
    source = pages(code)
    assert sum(t.count(old) for n, t in source if n == page_number) == 1
    return [(n, t.replace(old, new) if n == page_number else t) for n, t in source]


def check(source, year=2025):
    return check_general_income_reconciliation(source, find_income_statement_figures(source), report_year=year)


@pytest.mark.parametrize('code', ['600011', '600027', '600008'])
def test_actual_two_period_tax_and_attribution_rows_keep_sources_unchanged(code):
    source = pages(code)
    before = deepcopy(source)
    result = check(source)
    assert result['status'] == 'passed' and result['header_years'] == [2025, 2024]
    assert all(c['passed'] for c in result['checks'])
    assert source == before
    if code != '600027':
        assert result['operating_reconciliation']['status'] == 'missing_evidence'


@pytest.mark.parametrize('replacement', [
    '2025 年1—11 月', '2025 年2—12 月', '2025 年1—6 月', '2024 年1—12 月',
    '2025 年1—12 月\n2024 年度', '2025 年1—12 月\n2025 年度', '',
])
def test_relative_amount_columns_require_one_complete_correct_annual_period(replacement):
    assert check(changed('600011', 134, '2025 年1—12 月', replacement))['status'] != 'passed'


@pytest.mark.parametrize('replacement', [
    '上年发生额（未知）', '上年发生额（已重述2023）', '上年发生额（已重',
    '本年发生额', '上年发生额\n上年发生额', '2024 年度', '',
])
def test_relative_comparative_qualifiers_cannot_hide_extra_or_unknown_periods(replacement):
    assert check(changed('600027', 195, '上年发生额（已重\n述）', replacement))['status'] != 'passed'


def test_relative_header_is_bound_to_annual_subtitle_and_selected_report():
    assert check(pages('600027'), year=2024)['status'] != 'passed'
    assert check(changed('600027', 195, '\n2025 年度 \n', '\n2024 年度 \n'))['status'] != 'passed'


@pytest.mark.parametrize('replacement', ['', '2024 年1—6 月', '2025 年1—6 月'])
def test_restatement_relative_columns_cannot_lose_their_full_year_title(replacement):
    assert check(changed('600027', 195, '\n2025 年度 \n', '\n' + replacement + '\n'))['status'] != 'passed'


@pytest.mark.parametrize('year', [2024, 2026])
@pytest.mark.parametrize('unit_line', ['', '单位：人民币千元\n'])
def test_relative_continuation_year_cannot_override_the_first_table(year, unit_line):
    text = pages('600027')[0][1]
    before, after = text.split('三、营业利润', 1)
    source = [(195, before), (196, f'{year}年度\n{unit_line}项目\n附注\n本年发生额\n上年发生额（已重述）\n三、营业利润' + after)]
    assert check(source)['status'] != 'passed'


def test_pretax_cross_page_row_retains_exact_slices_and_amount_page():
    source = pages('600008')
    row = check(source)['evidence']['profit_before_tax']
    assert row['values'] == ['2936298518.05', '4882397416.54']
    assert row['pages'] == {'start': 114, 'end': 115}
    assert row['amount_pages'] == {'start': 114, 'end': 114}
    for segment in row['source_segments']:
        raw = dict(source)[segment['page_number']]
        assert raw[segment['start_offset']:segment['end_offset']] == segment['text']
    assert row['excerpt'].endswith('列）')


@pytest.mark.parametrize('page_number,old,new', [
    (114, '2025 年度\n2024 年度', '2024 年度\n2025 年度'),
    (114, '单位：元币种：人民币', '单位：元币种：港元'),
    (114, '单位：元币种：人民币', '单位：万元币种：人民币'),
    (114, '2,936,298,518.05\n4,882,397,416.54', '2,936,298,518.05'),
    (114, '2,936,298,518.05\n4,882,397,416.54', '2,936,298,518.05\n4,882,397,416.54\n999'),
    (114, '2,936,298,518.05', '2,,936,298,518.05'),
    (114, '2,936,298,518.05', 'NaN'),
    (114, '四、利润总额（亏损总额以“－”号填', '四、利润总额（亏损总额以“＋”号填'),
    (115, '北京首创生态环保集团股份有限公司2025 年年度报告', '其他集团股份有限公司2025 年年度报告'),
    (115, '\n115\n', '\n116\n'),
    (115, '\n列）\n', '\n未知行\n列）\n'),
    (115, '\n列）\n', '\n列）\n母公司利润表\n'),
    (115, '\n列）\n', '\n列）\n999\n'),
    (115, '七、76', '未知附注'),
    (115, '682,869,058.69', ''),
    (115, '737,930,098.21', '737,930,098.21\n999'),
])
def test_split_pretax_row_rejects_damaged_amounts_scope_units_and_boundaries(page_number, old, new):
    source = changed('600008', page_number, old, new)
    recovered = recover_cross_page_profit_before_tax(source, report_year=2025)
    assert recovered is None or recovered['values'] is None
    assert check(source)['status'] != 'passed'


@pytest.mark.parametrize('source', [pages('600008')[:1], list(reversed(pages('600008'))), pages('600008') + pages('600008')[-1:]])
def test_cross_page_profit_requires_adjacent_unique_pages(source):
    recovered = recover_cross_page_profit_before_tax(source, report_year=2025)
    assert recovered is None or recovered['values'] is None


def test_modified_actual_pretax_amount_is_a_mismatch_not_a_missing_cell():
    result = check(changed('600008', 114, '2,936,298,518.05', '2,936,298,519.05'))
    assert result['status'] == 'mismatch'
    assert result['checks'][0]['current']['difference'] == '1.00'


def test_numeric_note_and_one_amount_do_not_become_two_period_values():
    result = check(pages('600011'))
    detail = result['operating_reconciliation']
    assert detail['status'] == 'missing_evidence'
    assert 'fair_value_income' not in detail['evidence']
    assert '附注' in detail['note'] and '未补零' in detail['note']


@pytest.mark.parametrize('note', ['070', '７０', '００７０'])
def test_leading_zero_or_full_width_numeric_note_is_still_not_an_amount(note):
    result = check(changed('600011', 134, '\n70\n', '\n' + note + '\n'))
    assert result['operating_reconciliation']['status'] == 'missing_evidence'
    assert 'fair_value_income' not in result['operating_reconciliation']['evidence']


@pytest.mark.parametrize('tail', ['?999', '999元', '人民币999元', '￥999元', '？999'])
def test_extra_numeric_garbage_after_complete_net_profit_cells_is_rejected(tail):
    result = check(changed('600008', 115, '4,144,467,318.33\n', '4,144,467,318.33\n' + tail + '\n'))
    assert result['status'] != 'passed'


def test_true_blank_minority_cell_stays_missing_even_when_difference_would_be_zero():
    result = check(pages('300454'))
    assert result['status'] == 'missing_evidence'
    assert result['evidence']['minority_profit']['status'] == 'missing_or_ambiguous'
    assert result['checks'][0]['passed'] and not result['checks'][1]['passed']


@pytest.mark.parametrize('code,page,old', [('600011', 134, '2025 年1—12 月'), ('600027', 195, '2025 年度')])
def test_complete_year_cannot_hide_an_adjacent_conflicting_partial_period(code, page, old):
    assert check(changed(code, page, old, '2025 年度\n2024 年1—6 月'))['status'] != 'passed'


@pytest.mark.parametrize('year', [2024, 2026])
def test_same_line_relative_continuation_header_keeps_its_year_guard(year):
    text = pages('600027')[0][1]
    before, after = text.split('三、营业利润', 1)
    source = [(195, before), (196, f'{year}年度\n项目 附注 本年发生额 上年发生额（已重述）\n三、营业利润' + after)]
    assert check(source)['status'] != 'passed'
