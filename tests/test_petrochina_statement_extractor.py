"""Official PetroChina signed-table samples and fail-closed adversarial cases."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import re

import pytest

from src.petrochina_statement_extractor import (
    PETROCHINA_TEMPLATE, extract_petrochina_statements,
    is_petrochina_annual_report_identity,
)

SAMPLES = json.loads((Path(__file__).parent / 'fixtures/petrochina_signed_fourcols.json').read_text())
COMPANY = dict(code='601857', name='中国石油')


def pages(year=2025):
    return [(p['page_number'], p['text']) for p in next(s for s in SAMPLES if s['year'] == year)['pages']]


def replace(source, number, old, new):
    source = list(source)
    index = next(i for i, (n, _) in enumerate(source) if n == number)
    text = source[index][1]
    assert old in text, (number, old)
    source[index] = (number, text.replace(old, new, 1))
    return source


def rejected(source, year=2025):
    result = extract_petrochina_statements(source, year)
    assert result is None or (all(result[k] is None for k in ('income','balance','cash'))
                             and not result['income_reconciliation']['passed'])
    return result


@pytest.mark.parametrize('sample', SAMPLES, ids=lambda s: str(s['year']))
def test_both_official_reports_validate_all_four_columns_and_keep_source_pages(sample):
    source = [(p['page_number'], p['text']) for p in sample['pages']]
    assert is_petrochina_annual_report_identity(COMPANY, source, sample['year'])
    result = extract_petrochina_statements(source, sample['year'])
    assert result['template'] == PETROCHINA_TEMPLATE
    assert result['income_reconciliation']['passed']
    assert {k: len(v) for k, v in result['statement_reconciliation'].items()} == {'income':10,'balance':20,'cash':22}
    for kind in ('income','balance','cash'):
        for key, expected in sample['expected'][kind].items():
            assert result[kind][key] == expected
        for metric in result[kind]['metric_sources'].values():
            assert result[kind]['page_number'] <= metric['page_number'] <= result[kind]['end_page_number']
            assert '仅取合并列' in metric['statement']
        checks = result['statement_reconciliation'][kind]
        assert len({c['key'] for c in checks}) == len(checks)
        for c in checks:
            assert c['passed']
            for period in ('current','previous'):
                p = c[period]
                assert Decimal(p['left']) - Decimal(p['right']) == Decimal(p['difference'])
                assert abs(Decimal(p['difference'])) <= 1
    assert '中华人民共和国财政部颁布的企' in result['audit_evidence']['excerpt']


def test_2024_same_control_comparative_note_is_retained_without_replacing_values():
    result = extract_petrochina_statements(pages(2024), 2024)
    assert '同一控制下企业合并' in result['comparison_note']
    assert '2.70' in result['comparison_note']
    assert result['comparison_note'] in result['income']['metric_sources']['net_profit']['comparison_basis']
    assert result['income']['previous_net_profit'] == 161414


@pytest.mark.parametrize('company', [dict(code='601899', name='中国石油'), dict(code='601857', name='中国石化')])
def test_explicit_company_identity_must_match(company):
    assert not is_petrochina_annual_report_identity(company, pages(), 2025)


@pytest.mark.parametrize('old,new', [
    ('601857','601899'), ('中国石油天然气股份有限公司','中国石油集团工程股份有限公司'),
    ('2025 年度报告','2024 年度报告'), ('2025 年度报告','2025 年度报告摘要'),
    ('2025 年度报告','2025 年度报告英文'), ('A 股股票代码','H 股股票代码'),
])
def test_cover_code_legal_name_year_summary_language_and_share_class_are_bound(old,new):
    source = replace(pages(), 1, old, new)
    assert not is_petrochina_annual_report_identity(COMPANY, source, 2025)
    assert extract_petrochina_statements(source, 2025) is None


def test_legal_name_field_is_required_in_front_matter():
    source = replace(pages(), 4, '公司注册中文名称：', '其他公司的中文名称：')
    assert extract_petrochina_statements(source, 2025) is None


@pytest.mark.parametrize('year', [2023, 2026, True, '2025'])
def test_unsupported_years_do_not_enter_profile(year):
    assert extract_petrochina_statements(pages(), year) is None


@pytest.mark.parametrize('change', ['missing','wrong_standard','wrong_year','wrong_issuer','duplicate'])
def test_china_gaap_audit_must_be_unique_and_tied_to_selected_statement_set(change):
    source = pages()
    if change == 'missing': source = [(n,t) for n,t in source if n != 101]
    if change == 'wrong_standard': source = replace(source,101,'中华人民共和国财政部颁布的企\n业会计准则','国际财务报告准则')
    if change == 'wrong_year': source = replace(source,101,'2025 年12 月31 日的合并及公司资产负债表','2024 年12 月31 日的合并及公司资产负债表')
    if change == 'wrong_issuer': source = replace(source,101,'中国石油天然气股份有限公司全体股东','另一公司全体股东')
    if change == 'duplicate': source = sorted(source+[(102, next(t for n,t in source if n==101))])
    result = rejected(source)
    assert result['income_reconciliation']['status'] == 'missing_evidence'


@pytest.mark.parametrize('number,old,new', [
    (107,'2024 年12 月31 日','2023 年12 月31 日'),
    (108,'2024 年12 月31 日','2025 年12 月31 日'),
    (109,'2024 年度','2023 年度'), (110,'2024 年度','2025 年度'),
    (109,'合并 \n合并 \n公司 \n公司','合并 \n公司 \n合并 \n公司'),
    (110,'合并 \n合并 \n公司 \n公司','公司 \n公司 \n合并 \n合并'),
    (107,'人民币百万元','人民币千元'), (108,'人民币百万元','美元'),
    (109,'人民币百万元','人民币元'), (110,'人民币百万元','港元'),
    (109,'中国石油天然气股份有限公司','中国石化股份有限公司'),
])
def test_each_table_header_year_scope_currency_and_company_must_match(number,old,new):
    assert rejected(replace(pages(),number,old,new))['income_reconciliation']['status'] == 'missing_evidence'


@pytest.mark.parametrize('change', ['missing_continuation','gap','reordered','duplicate_table','missing_title'])
def test_statement_pages_are_unique_consecutive_and_explicit(change):
    source = pages()
    if change == 'missing_continuation': source = [(n,t) for n,t in source if n != 108]
    if change == 'gap': source = [(n+1 if n >=108 else n,t) for n,t in source]
    if change == 'reordered': source = list(reversed(source))
    if change == 'duplicate_table': source = source+[(200,next(t for n,t in source if n==110))]
    if change == 'missing_title': source = replace(source,108,'资产负债表(续)','资产负债表附注')
    rejected(source)


@pytest.mark.parametrize('number,old,new', [
    # Group current, group prior, company current, company prior tax cells.
    (109,'(54,144)','(54,147)'), (109,'(57,755)','(57,758)'),
    (109,'(26,270)','(26,273)'), (109,'(27,741)','(27,744)'),
    # The unused company columns must not evade income checks.
    (109,'1,730,507','1,730,510'), (109,'1,810,603','1,810,606'),
    (109,'14,703','14,706'), (109,'19,071','19,074'),
    # Component checks, not just accounting-equation totals.
    (107,'238,908','238,911'), (107,'216,246','216,249'),
    (107,'39,250','39,253'), (107,'25,199','25,202'),
    (108,'34,513','34,516'), (108,'45,955','45,958'),
    (108,'36,317','36,320'), (108,'49,315','49,318'),
    # Operating cash and cash roll-forward in every column.
    (110,'412,510','412,513'), (110,'406,532','406,535'),
    (110,'302,630','302,633'), (110,'322,454','322,457'),
    (110,'206,162','206,165'), (110,'172,477','172,480'),
    (110,'35,673','35,676'), (110,'25,139','25,142'),
    (110,'99,678','99,681'), (110,'(103)','(106)'),
    (110,'(616,837)','(616,840)'), (110,'(1,785)','(1,788)'),
])
def test_changed_current_comparative_parent_components_and_totals_fail(number,old,new):
    result = rejected(replace(pages(),number,old,new))
    assert result['income_reconciliation']['status'] == 'mismatch'
    assert any(not c['passed'] for rows in result['statement_reconciliation'].values() for c in rows)


@pytest.mark.parametrize('number,old,new', [
    (109,'(54,144)','54,144'), (109,'(2,246,121)','2,246,121'),
    (109,'(12,032)','12,032'), (110,'(2,057,292)','2,057,292'),
    (110,'(2,767,976)','2,767,976'), (110,'(111,199)','111,199'),
    (110,'3,080,808','(3,080,808)'),
])
def test_expense_and_cash_flow_signs_cannot_be_changed_even_if_layout_is_same(number,old,new):
    result = rejected(replace(pages(),number,old,new))
    assert result['income_reconciliation']['status'] == 'missing_evidence'
    assert '正负呈列' in result['failure_reason']


@pytest.mark.parametrize('replacement', ['54,144.5','54,,144','54,144xyz','N/A','','(54,144','54,144)'])
def test_malformed_missing_or_fractional_cells_are_not_guessed(replacement):
    assert rejected(replace(pages(),109,'(54,144)',replacement))['income_reconciliation']['status'] == 'missing_evidence'


@pytest.mark.parametrize('replacement', ['(54,144)\n777', '(54,144)\n777,,777', '(54,144)\n777xyz'])
def test_extra_good_or_damaged_cells_are_rejected(replacement):
    assert rejected(replace(pages(),109,'(54,144)',replacement))['income_reconciliation']['status'] == 'missing_evidence'


@pytest.mark.parametrize('token', ['777', '777,,777', '777xyz'])
def test_extra_cells_after_the_final_four_values_cannot_be_hidden_as_a_footer(token):
    source = replace(pages(),110,'后附财务报表附注为财务报表的组成部分',token+'\n后附财务报表附注为财务报表的组成部分')
    assert rejected(source)['income_reconciliation']['status'] == 'missing_evidence'


def test_missing_note_cannot_be_filled_by_a_number_or_previous_row():
    source = replace(pages(),109,'减：所得税费用 \n55','减：所得税费用 \n54')
    assert rejected(source)['income_reconciliation']['status'] == 'missing_evidence'


def test_unknown_or_duplicate_expense_rows_are_not_silently_skipped():
    source = replace(pages(),109,'减：所得税费用','其他费用\n1\n1\n1\n1\n减：所得税费用')
    assert rejected(source)['income_reconciliation']['status'] == 'missing_evidence'
    source = replace(pages(),109,'减：所得税费用','利润总额\n226,149\n241,502\n168,504\n172,768\n减：所得税费用')
    assert rejected(source)['income_reconciliation']['status'] == 'missing_evidence'


def test_company_minority_cash_components_cannot_exceed_their_parent_rows():
    source = replace(pages(),110,'10,795','211,199')
    assert '现金子项目超过' in rejected(source)['failure_reason']


@pytest.mark.parametrize('year', [2024,2025])
@pytest.mark.parametrize('column', [0,1])
@pytest.mark.parametrize('label,next_label,token', [
    ('其中：子公司吸收少数股东投资收到的现金','取得借款收到的现金','777'),
    ('其中：子公司支付给少数股东的股利、利润','支付其他与筹资活动有关的现金','(777)'),
])
def test_company_columns_cannot_contain_subsidiary_minority_cash(year,column,label,next_label,token):
    source=pages(year); number=116 if year==2024 else 110
    text=next(t for n,t in source if n==number)
    start=text.index(label); end=text.index(next_label,start)
    row=text[start:end]
    zero_cells=list(re.finditer(r'(?m)^[ \t]*-[ \t]*$',row))
    assert len(zero_cells)==2
    cell=zero_cells[column]
    changed=row[:cell.start()]+token+row[cell.end():]
    result=rejected(replace(source,number,row,changed),year)
    assert '公司列包含非零子公司少数股东现金项目' in result['failure_reason']


def test_two_reports_keep_their_own_comparative_years():
    previous = extract_petrochina_statements(pages(2024),2024)
    current = extract_petrochina_statements(pages(2025),2025)
    assert current['income_reconciliation']['header_years'] == [2025,2024]
    assert previous['income_reconciliation']['header_years'] == [2024,2023]
    assert current['income']['previous_net_profit'] == previous['income']['current_net_profit']
    assert current['income']['previous_net_profit'] != previous['income']['previous_net_profit']
