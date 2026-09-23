"""Operating revenue cannot be replaced by a readable total-income row."""
import json
from pathlib import Path

import pytest

from src.financial_statement_extractor import extract_income_statement_figures, find_income_statement_figures


SOURCE = json.loads((Path(__file__).parent / 'fixtures/powerchina_income_note_2025.json').read_text())
REVENUE_LINE = '五、（六十五）645,604,120,331.32 633,865,040,639.72'


def changed(old, new):
    assert sum(text.count(old) for _, text in SOURCE['pages']) == 1
    return [(number, text.replace(old, new)) for number, text in SOURCE['pages']]


def test_powerchina_prefers_actual_operating_revenue_over_larger_total_income():
    result = find_income_statement_figures(SOURCE['pages'])
    assert result is not None
    assert (result['current_revenue'], result['previous_revenue']) == (645604120331.32, 633865040639.72)
    assert result['current_revenue'] != 646237283223.32
    assert result['previous_revenue'] != 634732354204.98
    assert result['current_net_profit'] == 10007143581.45
    assert result['previous_net_profit'] == 12020193928.57
    assert result['unit'] == '人民币元'
    assert (result['page_number'], result['end_page_number']) == (122, 123)


@pytest.mark.parametrize('note', ('五、(六十五)', '五、（六十五）', '五(六十\n五)'))
@pytest.mark.parametrize('layout', ('same_line', 'split_values', 'separate_note'))
def test_only_exact_note_and_complete_two_period_cells_are_recovered(note, layout):
    values = ('645,604,120,331.32 633,865,040,639.72' if layout == 'same_line'
              else '645,604,120,331.32\n633,865,040,639.72')
    replacement = note + ('\n' if layout == 'separate_note' else '') + values
    result = find_income_statement_figures(changed(REVENUE_LINE, replacement))
    assert result and result['current_revenue'] == 645604120331.32
    assert result['previous_revenue'] == 633865040639.72


@pytest.mark.parametrize('replacement', (
    '五、（六十五）633,865,040,639.72',
    '五、（六十五）645,604,120,331.32',
    '五、（六十五）',
    '',
    REVENUE_LINE + ' 1.00',
    REVENUE_LINE + '\n1.00',
    REVENUE_LINE + '\nNaN',
    REVENUE_LINE + '\n123.1.2',
    REVENUE_LINE + '\n+123',
    REVENUE_LINE + '\n无数据',
    '五、（六十五）无关科目\n645,604,120,331.32 633,865,040,639.72',
    '五、（六十五）\n无关科目\n645,604,120,331.32 633,865,040,639.72',
    '无关科目\n' + REVENUE_LINE,
    '五、（六十五）645,,604,120,331.32 633,865,040,639.72',
    '五、（六十五）' + '9' * 100 + ' 633,865,040,639.72',
))
def test_missing_extra_malformed_or_borrowed_amounts_do_not_fall_back_to_total(replacement):
    assert find_income_statement_figures(changed(REVENUE_LINE, replacement)) is None


@pytest.mark.parametrize('note', ('五、、（六十五）', '五、（六十五', '五、六十五）',
    '五、（A）', '五、（六十五.1）', '五、（六十五)', '五、(六十五）'))
def test_bad_note_cannot_authorize_amount_recovery_or_total_fallback(note):
    assert find_income_statement_figures(changed(REVENUE_LINE,
        note + '645,604,120,331.32 633,865,040,639.72')) is None


@pytest.mark.parametrize('header', ('项目\n2025 年度\n2024 年度',
    '项目\n附注\n2024 年度\n2025 年度',
    '项目\n附注\n2025 年度\n2024 年度\n2023年度',
    '项目\n附注\n2025 年度\n2023 年度',
    '项目\n附注\n2025 年度',
    '项目\n附注\n本年发生额\n上年发生额'))
def test_recovery_requires_explicit_note_and_ordered_two_year_columns(header):
    assert find_income_statement_figures(changed('项目\n附注\n2025 年度\n2024 年度', header)) is None


@pytest.mark.parametrize('unit', ('', '单位：元币种：美元', '单位：港元', '单位：元币种：人民币\n单位：千元'))
def test_missing_foreign_or_conflicting_unit_cannot_authorize_note_recovery(unit):
    assert find_income_statement_figures(changed('单位：元币种：人民币', unit)) is None


def test_duplicate_operating_revenue_is_ambiguous_even_if_one_row_is_readable():
    duplicated = REVENUE_LINE + '\n其中：营业收入\n100.00 200.00'
    assert find_income_statement_figures(changed(REVENUE_LINE, duplicated)) is None


def test_unreadable_group_row_does_not_borrow_readable_parent_revenue_or_total():
    source = changed(REVENUE_LINE, '')
    number, text = source[-1]
    source[-1] = (number, text + '\n母公司利润表\n其中：营业收入\n' + REVENUE_LINE + '\n')
    assert find_income_statement_figures(source) is None


def test_malformed_same_line_revenue_note_still_prevents_total_fallback():
    source = changed('其中：营业收入\n' + REVENUE_LINE, '其中：营业收入坏附注\n' + REVENUE_LINE)
    assert find_income_statement_figures(source) is None


def test_legacy_total_only_layout_is_preserved_but_empty_operating_row_is_not():
    legacy = '''合并利润表
单位：元
一、营业总收入 1200.00 1100.00
归属于母公司股东的净利润 200.00 180.00
'''
    result = extract_income_statement_figures(1, legacy)
    assert result and result['current_revenue'] == 1200
    assert result['previous_revenue'] == 1100
    incomplete = legacy.replace('归属于母公司', '其中：营业收入\n归属于母公司')
    assert extract_income_statement_figures(1, incomplete) is None


def test_all_previous_general_income_source_values_remain_unchanged():
    # These earlier fixtures contain real operating rows and heterogeneous
    # valid note layouts, including the four-column Midea layout.
    samples = json.loads((Path(__file__).parent / 'fixtures/general_income_reconciliation_real.json').read_text())
    for sample in samples:
        result = find_income_statement_figures(sample['pages'])
        assert result is not None, sample['code']
        for field in ('current_revenue', 'previous_revenue', 'current_net_profit', 'previous_net_profit'):
            assert result[field] == sample['income'][field], (sample['code'], field)


@pytest.mark.parametrize('filename,code', [('industry_expansion_10.json', '600276'),
    ('industry_expansion_10.json', '600309'), ('industry_expansion_10.json', '601985'),
    ('bse_expansion_2025_statements.json', '920368')])
def test_existing_compact_note_and_numbered_parent_layouts_keep_source_amounts(filename, code):
    samples = json.loads((Path(__file__).parent / 'fixtures' / filename).read_text())
    sample = next(sample for sample in samples if sample['code'] == code)
    source = [(page['page_number'], page['text']) for page in sample['pages']]
    result = find_income_statement_figures(source)
    assert result is not None
    for key, metric in [('revenue', 'revenue'), ('net_profit', 'net_profit')]:
        assert result['current_' + key] == sample['expected'][metric]['current_yuan']
        assert result['previous_' + key] == sample['expected'][metric]['previous_yuan']


@pytest.mark.parametrize('note', ('七61', '七9', '七999'))
def test_compact_note_is_recognised_only_under_explicit_note_header(note):
    modified = changed(REVENUE_LINE, note + '\n645,604,120,331.32 633,865,040,639.72')
    assert find_income_statement_figures(modified)['current_revenue'] == 645604120331.32
    modified = [(number, text.replace('项目\n附注\n', '项目\n说明\n')) for number, text in modified]
    assert find_income_statement_figures(modified) is None


@pytest.mark.parametrize('note', ('七061', '七1000', '七61元', '七61 645,604,120,331.32', '七61645,604,120,331.32'))
def test_compact_note_does_not_guess_or_split_ambiguous_digits(note):
    modified = changed(REVENUE_LINE, note + '\n645,604,120,331.32 633,865,040,639.72')
    assert find_income_statement_figures(modified) is None


@pytest.mark.parametrize('parent', ('（四）母公司利润表', '(四) 母公司利润表', '四、母公司利润表'))
def test_numbered_parent_table_cannot_supply_missing_group_revenue(parent):
    group = '''合并利润表
单位：元
一、营业总收入 1200.00 1100.00
其中：营业收入
归属于母公司股东的净利润 200.00 180.00
'''
    text = group + parent + '\n营业收入 1000.00 900.00\n归属于母公司股东的净利润 100.00 90.00\n'
    assert extract_income_statement_figures(1, text) is None
