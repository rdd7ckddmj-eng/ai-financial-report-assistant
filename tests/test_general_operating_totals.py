"""Explicit total rows and their children must never both enter operating profit."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path

import pytest

from src.general_income_reconciliation import check_general_income_reconciliation
from src.financial_statement_extractor import find_income_statement_figures
from src.general_operating_reconciliation import _TOTAL_ALIASES, _DETAILS
from test_general_operating_reconciliation import ROWS, table

FIXTURES = Path(__file__).parent / 'fixtures'
ROWS_TOTAL = [
    ('营业总收入', '1007.00', '907.00'),
    ('其中：营业收入', '1000.00', '900.00'),
    ('利息收入', '3.00', '3.00'),
    ('已赚保费', '0.00', '0.00'),
    ('手续费及佣金收入', '4.00', '4.00'),
    ('营业总成本', '643.00', '563.00'),
    ('其中：营业成本', '500.00', '400.00'),
    ('利息支出', '6.00', '6.00'),
    ('手续费及佣金支出', '7.00', '7.00'),
    ('退保金', '0.00', '0.00'),
    ('赔付支出净额', '0.00', '0.00'),
    ('提取保险责任合同准备金净额', '0.00', '0.00'),
    ('保单红利支出', '0.00', '0.00'),
    ('分保费用', '0.00', '0.00'),
    *ROWS[2:13],
    ('汇兑收益', '-2.00', '-2.00'),
    ('净敞口套期收益', '3.00', '3.00'),
    *ROWS[13:17],
    ('营业利润', '376.00', '356.00'),
    ('加：营业外收入', '8.00', '7.00'),
    ('减：营业外支出', '9.00', '6.00'),
    ('利润总额', '375.00', '357.00'),
    ('减：所得税费用', '80.00', '72.00'),
    ('净利润', '295.00', '285.00'),
    ('归属于母公司股东的净利润', '275.00', '265.00'),
    ('少数股东损益', '20.00', '20.00'),
]


def income():
    return dict(unit='人民币元', page_number=10, end_page_number=10,
        current_revenue='1000.00', previous_revenue='900.00',
        current_net_profit='275.00', previous_net_profit='265.00')


def check(rows=None, *, text=None, figures=None, pages=None):
    return check_general_income_reconciliation(pages or [(10, text or table(ROWS_TOTAL if rows is None else rows))],
        figures or income(), report_year=2025)


def extra(result):
    return result['operating_reconciliation']


def source(code, name='general_income_reconciliation_real.json'):
    return deepcopy(next(s for s in json.loads((FIXTURES / name).read_text()) if s['code'] == code))


def real_check(sample):
    pages = [(p['page_number'], p['text']) if isinstance(p, dict) else p for p in sample['pages']]
    figures = sample.get('income') or find_income_statement_figures(pages)
    return check_general_income_reconciliation(pages, figures, report_year=sample['year'])


def test_total_formula_separates_child_roles_and_negative_signs():
    result = check(); op = extra(result)
    assert result['passed'] and op['passed'] and op['layout'] == 'explicit_totals'
    assert len(result['checks']) == 8 and len(op['checks']) == 5
    assert op['checks'][0]['current']['left'] == '376.00'
    assert op['checks'][0]['previous']['left'] == '356.00'
    assert op['evidence']['total_operating_cost']['coefficient'] == -1
    assert op['evidence']['financial_expense']['values'] == ['-10.00', '10.00']
    assert op['evidence']['credit_impairment']['values'] == ['-3.00', '-3.00']
    for key in ('operating_revenue', 'operating_cost', 'financial_expense', 'interest_revenue', *_DETAILS):
        assert op['evidence'][key]['coefficient'] == 0
    assert op['evidence']['interest_revenue']['values'] == ['3.00', '3.00']
    assert op['evidence']['interest_income_detail']['values'] == ['12.00', '12.00']
    subchecks = [c for c in op['checks'] if c.get('scope') == 'explicitly_listed_children']
    assert len(subchecks) == 2
    assert 'interest_income_detail' not in subchecks[1]['evidence_keys']
    assert '不将未列示项目认定为零' in subchecks[0]['note']


@pytest.mark.parametrize('key', [key for key in _TOTAL_ALIASES if key not in _DETAILS])
@pytest.mark.parametrize('period', (0, 1))
def test_every_printed_parent_and_child_wrong_cell_blocks_both_periods(key, period):
    # Even a zero placeholder changed by 0.02 must not silently change adapter
    # or drop the entire check. It contradicts an explicit printed subtotal.
    row = extra(check())['evidence'][key]
    original = row['excerpt']
    values = row['values'][:]
    values[period] = str(Decimal(values[period]) + Decimal('.02'))
    changed = row['label'] + '\n' + '\n'.join(values)
    text = table(ROWS_TOTAL).replace(original.replace(' ｜ ', '\n'), changed, 1)
    result = check(text=text)
    assert result['status'] == 'mismatch' and not result['passed']
    assert extra(result)['status'] == 'mismatch'
    assert any(not c[('current', 'previous')[period]]['passed'] for c in extra(result)['checks'])


@pytest.mark.parametrize('key', ['operating_revenue', 'interest_revenue', 'earned_premium',
    'commission_revenue', 'total_operating_cost', 'operating_cost', 'interest_cost',
    'commission_cost', 'surrender_cost', 'claims_cost', 'insurance_reserve_cost',
    'policy_dividend_cost', 'reinsurance_cost', 'operating_taxes', 'financial_expense',
    'other_income', 'investment_income', 'fair_value_income', 'credit_impairment'])
def test_deleted_printed_rows_are_not_implicitly_complete_or_zero(key):
    row = extra(check())['evidence'][key]['excerpt'].replace(' ｜ ', '\n')
    result = check(text=table(ROWS_TOTAL).replace(row + '\n', '', 1))
    assert extra(result)['status'] == 'missing_evidence'
    assert len(result['checks']) == 3 and result['passed']


@pytest.mark.parametrize('key', ['total_operating_revenue', 'total_operating_cost',
    'operating_cost', 'financial_expense', 'credit_impairment', 'operating_profit', 'profit_before_tax'])
@pytest.mark.parametrize('damage', ['blank', 'one_column', 'duplicate', 'extra', 'malformed'])
def test_missing_duplicate_extra_and_damaged_cells_never_pass(key, damage):
    row = extra(check())['evidence'][key]
    original = row['excerpt'].replace(' ｜ ', '\n')
    changed = {
        'blank': row['label'],
        'one_column': row['label'] + '\n' + row['values'][0],
        'duplicate': original + '\n' + original,
        'extra': original + '\n0.00',
        'malformed': original + '\n1,,000',
    }[damage]
    result = check(text=table(ROWS_TOTAL).replace(original, changed, 1))
    assert extra(result)['status'] == 'missing_evidence'
    assert extra(result)['checks'] == []


@pytest.mark.parametrize('unknown', ['未知收益\n0.00\n0.00', '其中：其他子项\n1.00\n1.00',
    '2025年年度报告全文\n10', 'NaN', '无数据'])
def test_unknown_rows_even_zero_are_not_discarded(unknown):
    result = check(text=table(ROWS_TOTAL).replace('营业利润\n', unknown + '\n营业利润\n'))
    assert extra(result)['status'] == 'missing_evidence'


def test_blank_optional_gains_are_not_zero_even_when_totals_would_balance():
    rows = [(n, '0.00', '0.00') if n in ('汇兑收益', '净敞口套期收益') else
        (n, '375.00', '355.00') if n == '营业利润' else
        (n, '374.00', '356.00') if n == '利润总额' else
        (n, '294.00', '284.00') if n == '净利润' else
        (n, '274.00', '264.00') if n == '归属于母公司股东的净利润' else (n, a, b)
        for n, a, b in ROWS_TOTAL]
    figures = income(); figures.update(current_net_profit='274.00', previous_net_profit='264.00')
    assert extra(check(rows, figures=figures))['passed']
    text = table(rows).replace('汇兑收益\n0.00\n0.00', '汇兑收益')
    result = check(text=text, figures=figures)
    assert result['passed'] and len(result['checks']) == 3
    assert extra(result)['status'] == 'missing_evidence'


def test_income_children_are_not_added_again_and_output_is_not_total_revenue():
    result = check()
    assert extra(result)['checks'][0]['current']['left'] == '376.00'
    figures = income(); figures['current_revenue'] = '1007.00'
    result = check(figures=figures)
    assert result['status'] == 'mismatch'
    assert extra(result)['checks'][-1]['key'] == 'selected_operating_revenue'
    assert extra(result)['checks'][-1]['current']['difference'] == '-7.00'


def test_financial_interest_detail_cannot_move_to_the_revenue_section():
    text = table(ROWS_TOTAL).replace('利息收入\n12.00\n12.00\n', '')
    text = text.replace('营业总成本\n', '利息收入\n12.00\n12.00\n营业总成本\n')
    assert extra(check(text=text))['status'] == 'missing_evidence'


def test_parent_table_cannot_supply_missing_total_or_child_rows():
    text = table(ROWS_TOTAL).replace('其中：营业成本\n500.00\n400.00\n', '')
    text += '\n（四）母公司利润表\n其中：营业成本\n500.00\n400.00\n'
    assert extra(check(text=text))['status'] == 'missing_evidence'


def test_period_reversal_is_rejected_before_enhancement():
    result = check(text=table(ROWS_TOTAL).replace('2025年度\n2024年度', '2024年度\n2025年度'))
    assert result['status'] == 'missing_evidence' and not result['passed']
    assert not result.get('operating_reconciliation', {}).get('passed')


@pytest.mark.parametrize('code,fixture,check_count,selection', [
    ('002475', 'general_income_reconciliation_real.json', 5, 'operating_revenue'),
    ('601766', 'shanghai_2025_statements.json', 4, 'total_operating_revenue'),
])
def test_visually_checked_official_reports_reconcile_real_amounts(code, fixture, check_count, selection):
    sample = source(code, fixture); result = real_check(sample); op = extra(result)
    assert result['passed'] and op['passed']
    assert len(op['checks']) == check_count and op['selected_revenue_key'] == selection
    assert all(Decimal(c[p]['difference']) == 0 for c in op['checks'] for p in ('current', 'previous'))
    assert all(row['excerpt'] and len(row['values']) == 2 for row in op['evidence'].values())
    assert sample.get('pdf_sha256', sample.get('sha256')) in (
        '957556c331a237cc3235b63659e884c7e1e877b6460f06d5039159f1598e4e46',
        '52254f29206ef598b0ab52a5f359cc87c2cf8e5a48ff87057015267bda99bf3d')
    if code == '002475':
        assert op['evidence']['total_operating_revenue']['pages'] == {'start': 120, 'end': 120}
        assert op['evidence']['total_operating_cost']['pages'] == {'start': 121, 'end': 121}
        assert op['page_headers'][0]['page_number'] == 121
    else:
        assert 'operating_revenue' not in op['evidence']
        assert not any(c['key'] == 'total_revenue_listed_components' for c in op['checks'])
        assert '未宣称其等于营业收入' in op['note']


def test_visual_blank_cells_stay_missing_not_filled_from_balancing_difference():
    sample = source('000858'); result = real_check(sample)
    assert sample['pdf_sha256'] == '09133e1f44b3bb4b2cebe211529ad68f5b04b6be10b43870f2a78c947d5910a4'
    assert result['passed'] and len(result['checks']) == 3
    assert extra(result)['status'] == 'missing_evidence'
    assert extra(result)['checks'] == []


def test_nonfinancial_candidate_gate_blocks_complete_child_subtotal_contradiction():
    from test_income_reconciliation_integration import candidate
    from src.china_stock import build_company_identity
    from src.on_demand_financial_snapshot import build_on_demand_financial_snapshot, build_financial_snapshot_report_html

    sample = source('002475', 'general_industry_2025_statements.json')
    before = candidate(sample)
    assert before['status'] == 'ready_for_human_review'
    snapshot = build_on_demand_financial_snapshot(build_company_identity(sample['code'], sample['name']), before)
    assert '营业总收入减营业总成本' in build_financial_snapshot_report_html(snapshot)
    for page in sample['pages']:
        page['text'] = page['text'].replace('292,755,910,976.71', '292,755,911,076.71')
    changed = candidate(sample)
    assert changed['income_reconciliation']['status'] == 'mismatch'
    assert changed['status'] == 'needs_review'
    assert extra(changed['income_reconciliation'])['checks'][0]['passed']  # Main total formula is unchanged.
    blocked = build_on_demand_financial_snapshot(build_company_identity(sample['code'], sample['name']), changed)
    assert all(m['current_yuan'] is None and m['previous_yuan'] is None for m in blocked['metrics'])


def test_financial_candidates_keep_their_existing_sector_adapter():
    from src.audited_company_onboarding import build_candidate_report_result
    from src.china_stock import build_company_identity

    sample = json.loads((FIXTURES / 'cms_securities_2025_statements.json').read_text())
    result = build_candidate_report_result(build_company_identity(sample['company_code'], '招商证券'),
        dict(report_year=sample['report_year'], title='招商证券2025年年度报告', url=sample['source_url'],
             published_date='2026-03-28'), b'%PDF-source-page-fixture',
        [dict(page_number=n, text=text) for n, text in sample['pages']])
    assert result['status'] == 'ready_for_human_review'
    assert 'operating_reconciliation' not in (result.get('income_reconciliation') or {})

    from test_insurance_statement_extractor import candidate as insurance_candidate
    _, insurer = insurance_candidate()
    assert insurer['status'] == 'ready_for_human_review'
    assert 'operating_reconciliation' not in (insurer.get('income_reconciliation') or {})


def test_visual_audit_records_reference_unchanged_source_fixtures():
    records = json.loads((FIXTURES / 'general_operating_totals_visual_audit.json').read_text())
    assert len(records) == 3 and len({r['code'] for r in records}) == 3
    for record in records:
        sample = source(record['code'], record['source_fixture'])
        assert sample['source_url'] == record['source_url']
        assert sample.get('pdf_sha256', sample.get('sha256')) == record['pdf_sha256']
        result = extra(real_check(sample))
        assert result['status'] == record['expected_operating_status']
        assert len(result['checks']) == record['expected_check_count']
