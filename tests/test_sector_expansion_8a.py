"""Source-specific cross-sector report cases, including an unsupported loss layout."""
import copy
import json
from pathlib import Path

import pytest

from src.audited_company_onboarding import build_candidate_report_result
from src.china_stock import build_company_identity
from src.on_demand_financial_snapshot import build_on_demand_financial_snapshot

SAMPLES = json.loads((Path(__file__).parent / 'fixtures' /
                      'sector_expansion_8a.json').read_text())


def _sample(code):
    return copy.deepcopy(next(s for s in SAMPLES if s['code'] == code))


def _page(sample, number):
    return next(p for p in sample['pages'] if p['page_number'] == number)


def _candidate(sample):
    company = build_company_identity(sample['code'], sample['name'])
    report = dict(report_year=sample['year'],
                  title=f"{sample['name']}{sample['year']}年年度报告",
                  url=sample['source_url'], published_date=sample['published_date'])
    result = build_candidate_report_result(company, report, b'%PDF-real-page-fixture', sample['pages'])
    return result, build_on_demand_financial_snapshot(company, result)


@pytest.mark.parametrize('sample', [s for s in SAMPLES if s['expected_status'] == 'ready_for_human_review'],
                         ids=lambda s: f"{s['code']}-{s['year']}")
def test_real_sector_reports_preserve_amounts_units_and_source_pages(sample):
    candidate, snapshot = _candidate(sample)
    assert candidate['income_reconciliation']['status'] == 'passed'
    assert all(candidate['statement_checks'].values())
    assert snapshot['status'] == 'ready_for_human_review'
    for metric in snapshot['metrics']:
        expected = sample['expected'][metric['key']]
        assert metric['current_yuan'] == expected['current_yuan']
        assert metric['previous_yuan'] == expected['previous_yuan']
        assert metric['pages'] == expected['pages']
        assert metric['source']['original_unit'] == expected['original_unit']
        assert metric['source']['accounting_basis'] == '合并口径'
        assert metric['source']['excerpt_status'] == 'captured'


def test_sany_uses_operating_revenue_not_total_revenue_including_interest():
    sample = _sample('600031')
    assert '89,699,505' in _page(sample, 89)['text']
    _, snapshot = _candidate(sample)
    revenue = next(m for m in snapshot['metrics'] if m['key'] == 'revenue')
    assert revenue['source']['raw_current_value'] == 89_231_023
    assert revenue['source']['raw_previous_value'] == 77_773_391
    assert revenue['current_yuan'] == 89_231_023_000


def test_longi_split_negative_sign_remains_unsupported_without_inventing_a_sign():
    sample = _sample('601012')
    assert '-7,561,633,667.41\n-\n10,205,897,803.72' in _page(sample, 126)['text']
    candidate, snapshot = _candidate(sample)
    assert candidate['income_reconciliation']['status'] == 'missing_evidence'
    assert candidate['income_reconciliation']['evidence']['profit_before_tax']['status'] == 'missing_or_ambiguous'
    assert snapshot['status'] == 'needs_review'
    for metric in snapshot['metrics']:
        assert metric['current_yuan'] is None and metric['previous_yuan'] is None
        expected = sample['expected'][metric['key']]
        assert metric['source']['raw_current_value'] == expected['raw_current_value']
        assert metric['source']['raw_previous_value'] == expected['raw_previous_value']


def test_mobile_conflicting_continuation_unit_blocks_standardized_amounts():
    sample = _sample('600941')
    page = _page(sample, 87)
    assert '人民币百万元' in page['text']
    page['text'] = page['text'].replace('人民币百万元', '人民币千元')
    candidate, snapshot = _candidate(sample)
    # Pure arithmetic can still balance; conflicting scale must block release.
    balance = [m for m in snapshot['metrics'] if m['key'] in {'total_assets', 'total_liabilities'}]
    assert all(m['source']['original_unit'] == '' for m in balance)
    assert snapshot['status'] == 'needs_review'
    assert all(m['current_yuan'] is None for m in snapshot['metrics'])


def test_cosco_missing_consolidated_cash_flow_cannot_borrow_parent_row():
    sample = _sample('601919')
    page = _page(sample, 104)
    assert '经营活动产生的现金流量净额' in page['text']
    page['text'] = page['text'].replace('经营活动产生的现金流量净额', '标签缺失')
    assert '-52,094,443.52' in _page(sample, 105)['text']
    candidate, snapshot = _candidate(sample)
    assert not candidate['statement_checks']['cash_flow_statement_reconciled']
    assert snapshot['status'] == 'needs_review'
    assert all(m['current_yuan'] is None for m in snapshot['metrics'])
