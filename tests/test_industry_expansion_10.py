"""Five real 2025 candidates and one image-only annual-report boundary."""
import copy
import json
from pathlib import Path

import pytest

from src.audited_company_onboarding import build_candidate_report_result
from src.china_stock import build_company_identity
from src.on_demand_financial_snapshot import build_on_demand_financial_snapshot

SAMPLES = json.loads((Path(__file__).parent / 'fixtures' / 'industry_expansion_10.json').read_text())


def _sample(code):
    return copy.deepcopy(next(s for s in SAMPLES if s['code'] == code))


def _page(sample, number):
    return next(p for p in sample['pages'] if p['page_number'] == number)


def _candidate(sample):
    company = build_company_identity(sample['code'], sample['name'])
    report = dict(report_year=sample['year'], title=f"{sample['name']}{sample['year']}年年度报告",
                  url=sample['source_url'], published_date=sample['published_date'])
    result = build_candidate_report_result(company, report, b'%PDF-real-page-fixture', sample['pages'])
    return result, build_on_demand_financial_snapshot(company, result)


def _assert_withheld(snapshot):
    assert snapshot['status'] == 'needs_review'
    assert all(m['current_yuan'] is None and m['previous_yuan'] is None for m in snapshot['metrics'])


@pytest.mark.parametrize('sample', [s for s in SAMPLES if s['expected_status'] == 'ready_for_human_review'],
                         ids=lambda s: s['code'])
def test_real_2025_reports_keep_both_periods_units_and_pages(sample):
    candidate, snapshot = _candidate(sample)
    assert snapshot['status'] == 'ready_for_human_review'
    assert all(candidate['statement_checks'].values())
    assert candidate['income_reconciliation']['status'] == 'passed'
    for metric in snapshot['metrics']:
        expected = sample['expected'][metric['key']]
        assert metric['current_yuan'] == expected['current_yuan']
        assert metric['previous_yuan'] == expected['previous_yuan']
        assert metric['pages'] == expected['pages']
        assert metric['source']['original_unit'] == expected['original_unit']
        assert metric['source']['accounting_basis'] == '合并口径'
        assert metric['source']['excerpt_status'] == 'captured'


def test_saic_keeps_operating_revenue_separate_from_total_revenue():
    sample = _sample('600104')
    assert '656,243,812,081.18' in _page(sample, 69)['text']
    _, snapshot = _candidate(sample)
    revenue = next(m for m in snapshot['metrics'] if m['key'] == 'revenue')
    assert revenue['current_yuan'] == 646_152_101_889.30
    assert revenue['previous_yuan'] == 614_074_061_818.13


@pytest.mark.parametrize('code,tax_page', [('600309', 84), ('601985', 128)])
def test_compact_tax_note_is_evidence_not_a_third_amount(code, tax_page):
    sample = _sample(code)
    assert '减：所得税费用\n七76\n' in _page(sample, tax_page)['text']
    candidate, _ = _candidate(sample)
    evidence = candidate['income_reconciliation']['evidence']['income_tax']
    assert evidence['notes'] == ['七76']
    assert len(evidence['values']) == 2
    assert evidence['error'] is None


@pytest.mark.parametrize('code,tax_page', [('600309', 84), ('601985', 128)])
@pytest.mark.parametrize('bad_note', ['七0076', '七1000', '七76元'])
def test_corrupt_compact_note_cannot_release_standardized_amounts(code, tax_page, bad_note):
    sample = _sample(code)
    page = _page(sample, tax_page)
    page['text'] = page['text'].replace('减：所得税费用\n七76\n', f'减：所得税费用\n{bad_note}\n', 1)
    candidate, snapshot = _candidate(sample)
    assert not candidate['statement_checks']['income_statement_reconciled']
    _assert_withheld(snapshot)


@pytest.mark.parametrize('code,header_page', [('600309', 83), ('601985', 127)])
def test_compact_note_requires_real_note_column_header(code, header_page):
    sample = _sample(code)
    page = _page(sample, header_page)
    assert '附注\n2025 年度' in page['text']
    page['text'] = page['text'].replace('附注\n2025 年度', '说明\n2025 年度')
    candidate, snapshot = _candidate(sample)
    assert not candidate['statement_checks']['income_statement_reconciled']
    _assert_withheld(snapshot)


def test_missing_saic_consolidated_cash_cannot_borrow_parent_cash():
    sample = _sample('600104')
    # Both sections retain their actual figures; remove only consolidated label.
    assert '经营活动产生的现金流量净额' in _page(sample, 73)['text']
    assert '经营活动产生的现金流量净额' in _page(sample, 74)['text']
    _page(sample, 73)['text'] = _page(sample, 73)['text'].replace('经营活动产生的现金流量净额', '标签缺失')
    candidate, snapshot = _candidate(sample)
    assert not candidate['statement_checks']['cash_flow_statement_reconciled']
    _assert_withheld(snapshot)


def test_cscec_image_only_tables_do_not_borrow_summary_or_note_values():
    sample = _sample('601668')
    for number in (146, 147, 148, 149, 150, 153, 154):
        assert _page(sample, number)['text'] == ''
    # Readable non-statement notes contain real assets/ liabilities, but cannot
    # substitute for the unavailable main table and its checks.
    assert '3,560,679,818' in _page(sample, 309)['text']
    assert '2,738,171,656' in _page(sample, 309)['text']
    candidate, snapshot = _candidate(sample)
    assert not any(candidate['statement_checks'].values())
    _assert_withheld(snapshot)
