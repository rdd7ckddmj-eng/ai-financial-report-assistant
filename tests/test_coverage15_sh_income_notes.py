"""Real note forms and loss labels preserve exact amounts and table scope."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json

import pytest

from src.financial_statement_extractor import find_income_statement_figures
from src.general_income_reconciliation import check_general_income_reconciliation


SAMPLES = json.loads((Path(__file__).parent / 'fixtures/coverage15_sh_income_notes.json').read_text())


def sample(code):
    return deepcopy(next(row for row in SAMPLES if row['code'] == code))


def source(code):
    return [(page['page_number'], page['text']) for page in sample(code)['pages']]


def replace(pages, old, new, *, count=-1):
    assert any(old in text for _, text in pages), old
    return [(number, text.replace(old, new, count)) for number, text in pages]


def check(pages):
    figures = find_income_statement_figures(pages)
    return check_general_income_reconciliation(pages, figures, report_year=2025)


@pytest.mark.parametrize('code', ['600809', '600350', '600066', '600332', '601111', '600050'])
def test_actual_original_amounts_periods_and_physical_pages_are_preserved(code):
    saved = sample(code)
    assert hashlib.sha256(json.dumps(saved['pages'], ensure_ascii=False).encode()).hexdigest() == saved['original_text_sha256']
    pages = source(code); before = deepcopy(pages)
    figures = find_income_statement_figures(pages)
    assert [figures[k] for k in ('current_revenue', 'previous_revenue', 'current_net_profit', 'previous_net_profit')] == saved['expected_values']
    assert [figures['page_number'], figures['end_page_number']] == saved['expected_span']
    result = check_general_income_reconciliation(pages, figures, report_year=2025)
    assert result['passed'] and result['header_years'] == [2025, 2024]
    assert pages == before
    assert all(item['passed'] for item in result['checks'])


@pytest.mark.parametrize('code,note,tax_note', [
    ('600809', '注释61', '注释76'),
    ('600350', '七·61', '七·76'),
    ('600066', '七-46', '七-60'),
])
def test_new_notes_remain_source_evidence_and_never_become_amounts(code, note, tax_note):
    result = check(source(code))
    assert result['evidence']['income_tax']['notes'] == [tax_note]
    assert result['evidence']['income_tax']['values'][0] not in ('76', '60')
    assert note in ''.join(text for _, text in source(code))
    assert result['operating_reconciliation']['status'] == 'missing_evidence'


@pytest.mark.parametrize('code,note', [('600809', '注释61'), ('600350', '七·61'), ('600066', '七-46')])
@pytest.mark.parametrize('suffix', ['x', '、62', '0000', '\n999', '\nNaN', '\n/', '\n999元'])
def test_note_recovery_rejects_unknown_suffix_or_extra_amount(code, note, suffix):
    assert find_income_statement_figures(replace(source(code), note, note + suffix)) is None


@pytest.mark.parametrize('code,note', [('600809', '注释61'), ('600350', '七·61'), ('600066', '七-46')])
@pytest.mark.parametrize('replacement', ['未知附注', '注释0', '七-', '七·', '注释1000'])
def test_incomplete_or_unknown_note_does_not_borrow_the_next_account(code, note, replacement):
    assert find_income_statement_figures(replace(source(code), note, replacement)) is None


@pytest.mark.parametrize('code,amount', [
    ('600809', '38,718,257,657.74'),
    ('600350', '23,925,458,141.04'),
    ('600066', '41,426,173,982.34'),
])
@pytest.mark.parametrize('replacement', ['', 'NaN', '1,23,456.00', '100\n200', '100\n200\n300', '/', '不适用'])
def test_new_note_rows_require_exact_two_complete_numeric_cells(code, amount, replacement):
    assert find_income_statement_figures(replace(source(code), amount, replacement)) is None


@pytest.mark.parametrize('code', ['600809', '600350', '600066'])
@pytest.mark.parametrize('damage', ['no_note_header', 'wrong_current_year', 'wrong_prior_year', 'wrong_currency'])
def test_new_note_rows_require_explicit_header_periods_and_unit(code, damage):
    pages = source(code)
    if damage == 'no_note_header':
        pages = replace(pages, '附注七' if code == '600809' else '附注\n', '未知列\n')
    elif damage == 'wrong_current_year':
        pages = replace(pages, '2025 年度', '2026 年度')
    elif damage == 'wrong_prior_year':
        pages = replace(pages, '2024 年度', '2023 年度')
    else:
        pages = replace(pages, '币种：人民币', '币种：美元')
    assert not check(pages)['passed']


@pytest.mark.parametrize('code,tax_note,tax_amount', [
    ('600809', '注释76', '4,354,606,577.84'),
    ('600350', '七·76', '1,386,893,229.49'),
    ('600066', '七-60', '893,518,314.21'),
])
@pytest.mark.parametrize('damage', ['unknown_note', 'duplicate_note', 'inline_duplicate_note', 'extra_note', 'missing', 'extra', 'malformed', 'mismatch', 'parent_boundary'])
def test_tax_rows_fail_closed_for_invalid_or_contradictory_source(code, tax_note, tax_amount, damage):
    pages = source(code)
    if damage == 'unknown_note': pages = replace(pages, tax_note, tax_note + '不明')
    elif damage == 'duplicate_note': pages = replace(pages, tax_note, tax_note + '\n' + tax_note)
    elif damage == 'inline_duplicate_note': pages = replace(pages, tax_note, tax_note + ' ' + tax_note)
    elif damage == 'extra_note': pages = replace(pages, tax_amount, tax_amount + '\n' + tax_note)
    elif damage == 'missing': pages = replace(pages, tax_amount, '')
    elif damage == 'extra': pages = replace(pages, tax_amount, tax_amount + '\n777')
    elif damage == 'malformed': pages = replace(pages, tax_amount, '1,23,456.00')
    elif damage == 'mismatch': pages = replace(pages, tax_amount, '1.00')
    else: pages = replace(pages, '减：所得税费用', '母公司利润表\n减：所得税费用')
    result = check(pages)
    assert not result['passed']
    if damage == 'mismatch': assert result['status'] == 'mismatch'


@pytest.mark.parametrize('damage', ['missing_page', 'duplicate_page', 'wrong_page', 'parent_table', 'wrong_repeated_header'])
def test_three_page_shandong_cannot_cross_missing_or_foreign_page(damage):
    pages = source('600350')
    if damage == 'missing_page': pages.pop(1)
    elif damage == 'duplicate_page': pages.insert(1, pages[1])
    elif damage == 'wrong_page': pages[1] = (130, pages[1][1])
    elif damage == 'parent_table': pages[2] = (124, '母公司利润表\n' + pages[2][1])
    else: pages[1] = (123, '项目\n附注\n2026年度\n2024年度\n' + pages[1][1])
    assert not check(pages)['passed']


@pytest.mark.parametrize('damage', ['third_row', 'different_current', 'different_previous', 'missing_parent_cell', 'wrong_hierarchy', 'unknown_note', 'extra_note_amount', 'no_subtitle', 'wrong_columns'])
def test_baiyun_explicit_parent_and_child_revenue_must_be_unique_adjacent_and_identical(damage):
    pages = source('600332')
    parent = '一、营业收入\n五、（四十九）\n77,656,109,939.23\n74,992,820,473.56\n'
    if damage == 'third_row': pages = replace(pages, parent, parent + parent)
    elif damage == 'different_current': pages = replace(pages, parent, parent.replace('77,656,109,939.23', '77,656,109,940.23'))
    elif damage == 'different_previous': pages = replace(pages, parent, parent.replace('74,992,820,473.56', '74,992,820,474.56'))
    elif damage == 'missing_parent_cell': pages = replace(pages, parent, parent.replace('74,992,820,473.56\n', ''))
    elif damage == 'wrong_hierarchy': pages = replace(pages, '其中：营业收入', '营业收入')
    elif damage == 'unknown_note': pages = replace(pages, '五、（四十九）', '五、（四十A）')
    elif damage == 'extra_note_amount': pages = replace(pages, '五、（四十九）', '五、（四十九）999')
    elif damage == 'no_subtitle': pages = replace(pages, '2025年度', '')
    else: pages = replace(pages, '本期发生额\n上期发生额', '上期发生额\n本期发生额')
    assert find_income_statement_figures(pages) is None


def test_pure_loss_labels_preserve_original_negative_values_and_tax_subtraction():
    result = check(source('601111'))
    assert result['evidence']['profit_before_tax']['values'] == ['-1596707', '-1605198']
    assert result['evidence']['consolidated_net_profit']['values'] == ['-3524826', '-2450090']
    assert result['evidence']['attributable_profit']['values'] == ['-1770393', '-237305']
    assert result['evidence']['minority_profit']['values'] == ['-1754433', '-2212785']
    assert result['evidence']['income_tax']['values'] == ['1928119', '844892']
    assert result['unit'] == '人民币千元'


@pytest.mark.parametrize('old,new', [
    ('(1,770,393)', '1,770,393'),
    # The established integer-thousand rounding allowance is one unit.
    ('(1,754,433)', '(1,754,435)'),
    ('(2,212,785)', ''),
    ('(1,754,433)', '(1,754,433)\n777'),
    ('(1,754,433)', 'NaN'),
    ('净亏损', '净盈利'),
    ('亏损总额', '未知总额'),
    ('归属于母公司股东的净亏损', '母公司利润表\n归属于母公司股东的净亏损'),
])
def test_loss_label_support_does_not_guess_signs_missing_cells_or_unknown_scope(old, new):
    assert not check(replace(source('601111'), old, new))['passed']


def test_unicom_eps_na_does_not_select_the_sf_attribution_na_layout():
    pages = source('600050'); original = deepcopy(pages)
    assert '不适用' in pages[0][1].split('八、每股收益')[1]
    assert '不适用' not in pages[0][1].split('八、每股收益')[0]
    result = check(pages)
    assert result['passed']
    assert result['evidence']['attributable_profit']['values'] == ['9126662570', '9029899018', '5980726779', '5187286631']
    assert result['evidence']['minority_profit']['values'] == ['11661126852', '11570685242', '0', '0']
    assert len(result['checks']) == 5
    assert pages == original


@pytest.mark.parametrize('marker', ['不适用', '不适用\n不适用'])
def test_unicom_profit_na_cannot_borrow_the_unrelated_eps_exemption(marker):
    pages = replace(source('600050'), '9,126,662,570', marker)
    assert not check(pages)['passed']
