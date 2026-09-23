"""Official Shanghai issuer statement pages, with complete-PDF runs kept separately.

Fixtures preserve original page text and file provenance. These tests exercise
candidate routing; they do not claim to rerun identity checks on a complete PDF.
"""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from src.audited_company_onboarding import build_candidate_report_result
from src.china_stock import build_company_identity
from src.on_demand_financial_snapshot import build_on_demand_financial_snapshot


SAMPLES = json.loads(
    (Path(__file__).parent / 'fixtures/shanghai_2025_statements.json').read_text()
)


def _snapshot(sample, pages=None):
    company = build_company_identity(sample['code'], sample['name'])
    report = dict(
        report_year=sample['year'], title=f"{sample['name']}2025年年度报告",
        url=sample['source_url'], published_date=sample['published_date'],
    )
    candidate = build_candidate_report_result(
        company, report, b'%PDF-source-pages-fixture',
        sample['pages'] if pages is None else pages,
    )
    return build_on_demand_financial_snapshot(company, candidate)


@pytest.mark.parametrize('sample', SAMPLES, ids=lambda s: s['code'])
def test_official_shanghai_pages_preserve_both_year_amounts_and_units(sample):
    result = _snapshot(sample)
    assert result['status'] == 'ready_for_human_review'
    assert result['report']['statement_template'] == 'general'
    assert result['report']['source_url'] == sample['source_url']
    assert all(result['statement_checks'].values())
    assert result['income_reconciliation']['passed'] is True
    for metric in result['metrics']:
        expected = sample['expected'][metric['key']]
        assert metric['current_yuan'] == expected['current_yuan']
        assert metric['previous_yuan'] == expected['previous_yuan']
        assert metric['pages'] == expected['pages']
        assert metric['source']['raw_current_value'] == expected['raw_current_value']
        assert metric['source']['raw_previous_value'] == expected['raw_previous_value']
        assert metric['source']['original_unit'] == expected['unit']
        assert metric['source']['excerpt_status'] == 'captured'


@pytest.mark.parametrize('sample', SAMPLES, ids=lambda s: s['code'])
@pytest.mark.parametrize('period', ['raw_current_value', 'raw_previous_value'])
def test_income_attribution_mismatch_in_either_year_blocks_all_standard_amounts(sample, period):
    pages = deepcopy(sample['pages'])
    expected = sample['expected']['net_profit']
    value = expected[period]
    decimals = 2 if expected['unit'] == '元' else 0
    token = f'{value:,.{decimals}f}'
    replacement = f'{value + 1000:,.{decimals}f}'
    changed = False
    for page in pages:
        if expected['pages']['start'] <= page['page_number'] <= expected['pages']['end'] and token in page['text']:
            page['text'] = page['text'].replace(token, replacement, 1)
            changed = True
            break
    assert changed, 'Mutation must reach the observed attributable-profit cell.'
    result = _snapshot(sample, pages)
    assert result['status'] == 'needs_review'
    assert result['statement_checks']['income_statement_reconciled'] is False
    assert all(m['current_yuan'] is None and m['previous_yuan'] is None for m in result['metrics'])


def test_haier_incomplete_wrapped_sign_annotation_does_not_borrow_numeric_cells():
    sample = next(s for s in SAMPLES if s['code'] == '600690')
    pages = deepcopy(sample['pages'])
    page = next(p for p in pages if p['page_number'] == 123)
    original = '1.归属于母公司股东的净利润（净\n亏损以“-”号填列）'
    assert original in page['text']
    page['text'] = page['text'].replace(original, original[:-1], 1)
    result = _snapshot(sample, pages)
    assert result['status'] == 'needs_review'
    assert result['statement_checks']['income_statement_reconciled'] is False


def test_shenhua_net_decrease_preserves_negative_sign_and_cash_rollforward():
    sample = next(s for s in SAMPLES if s['code'] == '601088')
    pages = deepcopy(sample['pages'])
    page = next(p for p in pages if p['page_number'] == 163)
    assert '现金及现金等价物净减少额' in page['text']
    assert '(43,125)' in page['text']
    page['text'] = page['text'].replace('(43,125)', '43,125', 1)
    result = _snapshot(sample, pages)
    assert result['status'] == 'needs_review'
    assert result['statement_checks']['cash_flow_statement_reconciled'] is False
    assert all(m['current_yuan'] is None and m['previous_yuan'] is None for m in result['metrics'])
