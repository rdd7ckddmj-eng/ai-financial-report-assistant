"""Unchanged BSE report-page excerpts plus source-specific negative cases.

The fixture is not a PDF. Complete-PDF production receipts are recorded
separately; these cases preserve the exact consolidated amounts and page scope.
"""
import copy
import json
from pathlib import Path

import pytest

from src.audited_company_onboarding import build_candidate_report_result
from src.china_stock import build_company_identity
from src.on_demand_financial_snapshot import build_on_demand_financial_snapshot

SAMPLES = json.loads((Path(__file__).parent / 'fixtures' /
                      'bse_expansion_2025_statements.json').read_text())


def _candidate(sample):
    company = build_company_identity(sample['code'], sample['name'])
    report = dict(report_year=sample['year'],
                  title=f"{sample['name']}{sample['year']}年年度报告",
                  url=sample['source_url'], published_date=sample['published_date'])
    result = build_candidate_report_result(company, report, b'%PDF-real-page-fixture', sample['pages'])
    return result, build_on_demand_financial_snapshot(company, result)


def _sample(code):
    return copy.deepcopy(next(s for s in SAMPLES if s['code'] == code))


def _page(sample, number):
    return next(p for p in sample['pages'] if p['page_number'] == number)


@pytest.mark.parametrize('sample', SAMPLES, ids=lambda s: f"{s['code']}-{s['year']}")
def test_real_bse_reports_keep_consolidated_amounts_and_page_evidence(sample):
    candidate, snapshot = _candidate(sample)
    assert candidate['income_reconciliation']['status'] == 'passed'
    assert all(candidate['statement_checks'].values())
    assert snapshot['status'] == 'ready_for_human_review'
    for metric in snapshot['metrics']:
        expected = sample['expected'][metric['key']]
        assert metric['current_yuan'] == expected['current_yuan']
        assert metric['previous_yuan'] == expected['previous_yuan']
        assert metric['pages'] == expected['pages']
        assert metric['source']['accounting_basis'] == '合并口径'
        assert metric['source']['excerpt_status'] == 'captured'


def test_jinbo_page_header_does_not_become_an_extra_tax_amount():
    sample = _sample('920982')
    result, _ = _candidate(sample)
    tax = result['income_reconciliation']['evidence']['income_tax']
    assert tax['values'] == ['114649788.24', '126276216.02']
    assert tax['pages'] == {'start': 90, 'end': 90}
    assert ' ｜ 91' not in tax['excerpt']
    minority = result['income_reconciliation']['evidence']['minority_profit']
    assert minority['values'] == ['-6418461.52', '-1127086.71']


def test_linton_missing_consolidated_revenue_cannot_borrow_parent_revenue():
    sample = _sample('920368')
    page = _page(sample, 94)
    assert '营业总收入' in page['text'] and '其中：营业收入' in page['text']
    page['text'] = page['text'].replace('营业总收入', '收入标签缺失').replace('其中：营业收入', '其中：标签缺失')
    # The same window includes the parent table on p95 with 676,314,020.34.
    assert '676,314,020.34' in _page(sample, 95)['text']
    result, snapshot = _candidate(sample)
    assert result['income_reconciliation']['status'] == 'missing_evidence'
    assert snapshot['status'] == 'needs_review'
    assert all(m['current_yuan'] is None for m in snapshot['metrics'])


def test_jinbo_changed_minority_sign_is_a_mismatch_not_missing_evidence():
    sample = _sample('920982')
    page = _page(sample, 91)
    assert '-6,418,461.52' in page['text']
    page['text'] = page['text'].replace('-6,418,461.52', '6,418,461.52', 1)
    result, snapshot = _candidate(sample)
    assert result['income_reconciliation']['status'] == 'mismatch'
    assert snapshot['status'] == 'needs_review'
    assert all(m['current_yuan'] is None for m in snapshot['metrics'])


def test_btr_duplicate_attributable_row_remains_ambiguous():
    sample = _sample('920185')
    page = _page(sample, 96)
    page['text'] += '\n归属于母公司所有者的净利润\n930,224,441.05\n1,653,905,198.27\n'
    result, snapshot = _candidate(sample)
    assert result['income_reconciliation']['status'] == 'missing_evidence'
    assert result['income_reconciliation']['evidence']['attributable_profit']['status'] == 'missing_or_ambiguous'
    assert snapshot['status'] == 'needs_review'
    assert all(m['current_yuan'] is None for m in snapshot['metrics'])
