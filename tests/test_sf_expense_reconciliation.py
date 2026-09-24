"""Signed expenses and explicit company N/A cells need source evidence."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from src.financial_statement_extractor import find_income_statement_figures
from src.general_income_reconciliation import check_general_income_reconciliation

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/sf_express_combined_income_2025.json').read_text())


def pages():
    return [(p['page_number'], p['text']) for p in FIXTURE['pages']]


def check(source):
    # Retain the original candidate when probing the independent arithmetic
    # guard; extractor rejection alone must not hide a permissive verifier.
    income = find_income_statement_figures(pages())
    return check_general_income_reconciliation(source, income, report_year=2025)


def changed(page, old, new):
    assert sum(t.count(old) for n, t in pages() if n == page) == 1
    return [(n, t.replace(old, new) if n == page else t) for n, t in pages()]


def test_real_signed_tax_and_na_company_scope_are_explicit_not_zero():
    source = pages(); before = deepcopy(source)
    result = check(source)
    assert result['status'] == 'passed'
    assert source == before
    assert result['evidence']['income_tax']['values'] == ['-3233066', '-3388416', '-397', '-11227']
    assert result['checks'][0]['current']['left'] == '11684811'
    assert result['checks'][0]['previous']['left'] == '10218845'
    for key in ('attributable_profit', 'minority_profit'):
        evidence = result['evidence'][key]
        assert evidence['values'][2:] == [None, None]
        assert evidence['raw_values'][2:] == ['不适用', '不适用']
    assert 'profit_attribution_company' not in [c['key'] for c in result['checks']]
    assert result['not_applicable_checks'][0]['key'] == 'profit_attribution_company'
    assert '未计作通过' in result['note']
    assert result['operating_reconciliation']['status'] == 'unsupported_layout'
    spans = result['layout_recoveries'][0]['source_spans']
    assert [(s['page_number'], s['original_text']) for s in spans] == [(159, '158\n'), (160, '159\n')]
    presentation = result['signed_expense_presentation']
    assert len(presentation['evidence']) == 4
    assert '未通过试算选择' in presentation['note']


@pytest.mark.parametrize('old,new', [
    ('财务（费用）/收入', '财务费用'),
    ('财务（费用）/收入', '财务（费用）/收入\n财务（费用）/收入'),
    ('(267,178,276)', '267,178,276'),
    ('(764,777)', '-764,777'),
    ('(19,499,245)', '19,499,245'),
    ('(1,788,752)', '1,788,752'),
    ('8,161\n68,047', '(8,161)\n68,047'),
    ('四(43)', '未知附注'),
    ('四(43)', '四(43)\n四(44)'),
    ('四(43)', '四(43) 四(99)'),
    ('四(45)', '四(45) 四(99)'),
    ('四(47)', '四(47) 四(99)'),
    ('四(53)', '四(53)\n四(99)'),
    ('四(53)', '四(53) 四(99)'),
    ('(768)', '(768)\n999'),
    ('(768)', '(768)\nNaN'),
    ('(768)', '(768)\n未知说明'),
    ('(3,233,066)', '3,233,066'),
    ('(11,227)', '(11,227)\n999'),
    ('(11,227)', '(11,227)\n?999元'),
    ('(11,227)', '(11,227)\n未知附注\n999'),
    ('税金及附加', '未知费用'),
])
def test_unknown_or_contradictory_presentation_cannot_select_a_sign(old, new):
    assert check(changed(159, old, new))['status'] != 'passed'


@pytest.mark.parametrize('replacement', [
    '11,117,216\n10,170,427\n/\n/',
    '11,117,216\n10,170,427\n不适用',
    '11,117,216\n10,170,427\n不适用\n0',
    '11,117,216\n10,170,427\n不适用\n不适用\n999',
    '11,117,216\n不适用\n10,170,427\n不适用',
])
def test_company_na_cells_cannot_move_or_become_zero(replacement):
    original = '11,117,216\n10,170,427\n不适用\n不适用'
    assert check(changed(160, original, replacement))['status'] != 'passed'


def test_minority_company_values_cannot_replace_an_explicit_na_scope():
    source = changed(160, '567,595\n48,418\n不适用\n不适用', '567,595\n48,418\n0\n0')
    assert check(source)['status'] == 'missing_evidence'


def test_slash_compatibility_cannot_change_explicit_company_na_labels():
    source = changed(160, '567,595\n48,418\n不适用\n不适用', '567,595\n48,418\n/\n/')
    assert check(source)['status'] == 'missing_evidence'


@pytest.mark.parametrize('tail', ['未知附注\n999', '?999元', '不适用'])
def test_complete_minority_cells_cannot_hide_extra_tail(tail):
    source = changed(160, '567,595\n48,418\n不适用\n不适用',
                     '567,595\n48,418\n不适用\n不适用\n' + tail)
    assert check(source)['status'] != 'passed'


def test_wrong_issuer_and_year_header_cannot_fall_back_to_physical_page_number():
    source = changed(160, '159\n2025年度报告    顺丰控股股份有限公司', '160\n2024年度报告    其他股份有限公司')
    assert check(source)['status'] == 'missing_evidence'


@pytest.mark.parametrize('title', ['2025年度合并现金流量表', '2025年度合并及公司现金流量表',
                                   '2025年度母公司利润表', '2025年度合并资产负债表'])
def test_annual_prefixed_other_statement_header_stops_the_income_scope(title):
    source = changed(160, '第九节 财务报告\n项目', '第九节 财务报告\n' + title + '\n项目')
    assert check(source)['status'] != 'passed'


def test_changed_tax_amount_reports_mismatch_without_trying_the_other_direction():
    result = check(changed(159, '(3,233,066)', '(3,233,166)'))
    assert result['status'] == 'mismatch'
    assert result['checks'][0]['current']['difference'] == '-100'
    assert result['signed_expense_presentation']['kind'] == 'explicit_four_column_signed_expenses'


@pytest.mark.parametrize('old,new', [('159\n2025年度报告', '158\n2025年度报告'),
                                     ('159\n2025年度报告', '999\n2025年度报告')])
def test_unproven_printed_page_marker_is_not_deleted(old, new):
    assert check(changed(160, old, new))['status'] != 'passed'
