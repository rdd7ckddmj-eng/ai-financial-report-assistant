"""Sinopec CAS routing must remain source-bound through review and export."""
from copy import deepcopy
from datetime import date
from hashlib import sha256
import json
from pathlib import Path

import pytest

from src.audited_company_onboarding import build_candidate_report_result
from src.china_stock import build_company_identity
from src.financial_snapshot_review import (
    CORE_METRIC_KEYS, FinancialSnapshotReviewError,
    build_exportable_review_workpaper, build_financial_snapshot_review,
    confirm_snapshot_metric, serialise_review_workpaper,
)
from src.manual_financial_snapshot import build_manual_financial_snapshot
from src.on_demand_financial_snapshot import (
    build_financial_snapshot_report_html, build_on_demand_financial_snapshot,
)
from src.sinopec_statement_extractor import SINOPEC_TEMPLATE

SAMPLE = json.loads((Path(__file__).parent / 'fixtures/sinopec_2025_cas_million.json').read_text())
COMPANY = build_company_identity('600028', '中国石化')
PDF = b'%PDF-integration-fixture-only-not-an-original-PDF'
PAGES = {'revenue': 99, 'net_profit': 99, 'total_assets': 95,
         'total_liabilities': 96, 'operating_cash_flow': 102}
LABELS = {'revenue': '营业收入', 'net_profit': '母公司股东的净利润', 'total_assets': '资产总计',
          'total_liabilities': '负债合计', 'operating_cash_flow': '经营活动产生的现金流量净额'}


def _replace(sample, number, old, new):
    page = next(p for p in sample['pages'] if p['page_number'] == number)
    assert old in page['text']
    page['text'] = page['text'].replace(old, new, 1)


def _candidate(sample=None, company=None):
    sample = sample or SAMPLE
    return build_candidate_report_result(company or COMPANY,
        dict(report_year=sample['year'], published_date=sample['published_date'],
             title=f"中国石化{sample['year']}年年度报告", url=sample['source_url']),
        PDF, deepcopy(sample['pages']))


def _manual(monkeypatch, sample=None, company=None):
    sample = sample or SAMPLE
    monkeypatch.setattr('src.manual_financial_snapshot.extract_pdf_pages',
                        lambda *a, **kw: deepcopy(sample['pages']))
    return build_manual_financial_snapshot(company or COMPANY, PDF,
        report_year=sample['year'], source_url=sample['source_url'],
        published_date=sample['published_date'], identity_confirmed=True,
        today=date(2026, 9, 24))


def _assert_no_accepted_amounts(candidate, company=None):
    assert candidate['status'] == 'needs_review'
    assert candidate['statement_template'] == SINOPEC_TEMPLATE
    assert not any(candidate['statement_checks'].values())
    assert all(value is None for value in candidate['values'].values())
    assert candidate['extraction_note']
    snapshot = build_on_demand_financial_snapshot(company or COMPANY, candidate)
    assert snapshot['status'] == 'needs_review'
    assert all(m['current_yuan'] is None and m['previous_yuan'] is None for m in snapshot['metrics'])
    assert all(value is None for value in snapshot['ratios'].values())
    review = build_financial_snapshot_review(snapshot)
    with pytest.raises(FinancialSnapshotReviewError):
        build_exportable_review_workpaper(review)
    return snapshot


def test_real_fixture_candidate_uses_only_cas_and_preserves_each_raw_metric_source():
    result = _candidate()
    assert result['status'] == 'ready_for_human_review'
    assert result['statement_template'] == SINOPEC_TEMPLATE
    assert all(result['statement_checks'].values())
    assert result['income_reconciliation']['passed']
    assert result['income_reconciliation']['header_years'] == [2025, 2024]
    assert {k: len(v) for k,v in result['statement_reconciliation'].items()} == {'income':6,'balance':10,'cash':11}
    assert all(check['passed'] for checks in result['statement_reconciliation'].values() for check in checks)
    assert result['statement_pages'] == dict(income_statement=dict(start=99,end=99),
        balance_sheet=dict(start=95,end=96),cash_flow_statement=dict(start=102,end=102))
    assert result['evidence_fingerprint_sha256'] == sha256(PDF).hexdigest()
    for key, expected in SAMPLE['expected'].items():
        assert [result['values']['current_'+key],result['values']['previous_'+key]] == expected
        evidence = result['metric_evidence'][key]
        assert [evidence['raw_current_value'],evidence['raw_previous_value']] == expected
        assert evidence['pages'] == dict(start=PAGES[key],end=PAGES[key])
        assert evidence['original_unit'] == '人民币百万元'
        assert evidence['excerpt_status'] == 'captured'
        assert LABELS[key] in evidence['excerpt']
        assert all(format(value, ',') in evidence['excerpt'] for value in expected)
        assert '中国企业会计准则合并报表' in evidence['statement']
        assert 'CAS合并报表2024比较栏原值' in evidence['comparison_basis']
    assert result['values']['current_net_profit'] not in (35250,35633,32476)
    json.dumps(result, ensure_ascii=False, allow_nan=False)


def test_manual_builder_normalises_both_periods_without_losing_cas_scope(monkeypatch):
    snapshot = _manual(monkeypatch)
    assert snapshot['status'] == 'ready_for_human_review'
    assert snapshot['input_provenance'] == 'user_uploaded_official_report_candidate'
    assert snapshot['report']['statement_template'] == SINOPEC_TEMPLATE
    assert snapshot['report']['source_url'] == SAMPLE['source_url']
    assert snapshot['source_fingerprint_sha256'] == sha256(PDF).hexdigest()
    for metric in snapshot['metrics']:
        expected = SAMPLE['expected'][metric['key']]
        assert [metric['current_yuan'],metric['previous_yuan']] == [v*1_000_000 for v in expected]
        assert metric['pages'] == dict(start=PAGES[metric['key']],end=PAGES[metric['key']])
        assert [metric['source']['raw_current_value'],metric['source']['raw_previous_value']] == expected
        assert metric['source']['original_unit'] == '人民币百万元'
        assert metric['change_rate'] == pytest.approx((expected[0]-expected[1])/expected[1])
    assert snapshot['ratios']['net_profit_margin'] == pytest.approx(31809/2783583)
    assert snapshot['ratios']['operating_cash_conversion'] == pytest.approx(162496/31809)
    assert snapshot['ratios']['liabilities_to_assets'] == pytest.approx(1165845/2155617)
    html = build_financial_snapshot_report_html(snapshot)
    assert SAMPLE['source_url'] in html
    assert '中国企业会计准则合并报表' in html
    assert '资产负债与现金流金额关系' in html
    assert '31,809' in html and '50,313' in html
    json.dumps(snapshot, ensure_ascii=False, allow_nan=False)


def test_all_five_explicit_review_decisions_are_required_and_export_retains_source(monkeypatch):
    snapshot = _manual(monkeypatch)
    review = build_financial_snapshot_review(snapshot)
    assert review['status'] == 'pending_human_review'
    assert all(m['decision'] == 'pending' for m in review['metrics'])
    with pytest.raises(FinancialSnapshotReviewError):
        build_exportable_review_workpaper(review)
    for key in CORE_METRIC_KEYS[:-1]:
        review = confirm_snapshot_metric(review, key)
        with pytest.raises(FinancialSnapshotReviewError):
            build_exportable_review_workpaper(review)
    review = confirm_snapshot_metric(review, CORE_METRIC_KEYS[-1])
    workpaper = build_exportable_review_workpaper(review)
    assert workpaper['review_status'] == 'review_complete'
    assert workpaper['report']['statement_template'] == SINOPEC_TEMPLATE
    assert workpaper['source_fingerprint_sha256'] == sha256(PDF).hexdigest()
    for metric in workpaper['metrics']:
        current, previous = SAMPLE['expected'][metric['key']]
        assert metric['original_value_yuan'] == current*1_000_000
        assert metric['effective_value_yuan'] == current*1_000_000
        assert metric['source']['raw_previous_value'] == previous
        assert metric['source']['pages'] == dict(start=PAGES[metric['key']],end=PAGES[metric['key']])
        assert LABELS[metric['key']] in metric['source']['excerpt']
    assert workpaper['controls'] == dict(all_core_metrics_decided=True,
        automatic_extraction_is_verification=False,source_pdf_embedded=False)
    exported = serialise_review_workpaper(workpaper)
    assert '%PDF' not in exported and len(exported.encode()) < 64*1024


@pytest.mark.parametrize('page,old,new',[
    (99,'2,783,583','2,783,584'), (99,'3,074,562','3,074,563'),
    (99,'31,809','35,633'), (99,'50,313','45,295'),  # parent-company profit
    (99,'31,809','32,476'), (99,'50,313','48,939'),  # IFRS attributable profit
    (99,'7,934','7,935'), (99,'12,966','12,967'),
    (95,'2,155,617','2,155,618'), (96,'1,108,478','1,108,479'),
    (102,'162,496','162,497'), (102,'149,360','149,361'),
])
def test_changed_cas_values_fail_all_the_way_to_snapshot_and_export(page,old,new):
    sample = deepcopy(SAMPLE)
    _replace(sample,page,old,new)
    result = _candidate(sample)
    assert result['income_reconciliation']['status'] == 'mismatch'
    _assert_no_accepted_amounts(result)


@pytest.mark.parametrize('page',[89,95,96,99,102])
def test_missing_required_cas_pages_cannot_borrow_parent_or_ifrs(page):
    sample = deepcopy(SAMPLE)
    sample['pages'] = [p for p in sample['pages'] if p['page_number'] != page]
    assert {101,175,180}.issubset({p['page_number'] for p in sample['pages']})
    _assert_no_accepted_amounts(_candidate(sample))


@pytest.mark.parametrize('page,other',[(95,97),(96,98),(99,101),(99,175),(102,103),(102,180)])
def test_substituted_parent_or_ifrs_table_is_not_accepted_at_cas_page(page,other):
    sample = deepcopy(SAMPLE)
    old = next(p for p in sample['pages'] if p['page_number'] == page)
    old['text'] = next(p for p in sample['pages'] if p['page_number'] == other)['text']
    _assert_no_accepted_amounts(_candidate(sample))


@pytest.mark.parametrize('page,old,new',[
    (1,'2025 年度报告','2024 年度报告'),
    (236,'中国石油化工股份有限公司','中国石化上海石油化工股份有限公司'),
    (237,'股票代号：600028','股票代号：600688'),
    (237,'A 股： \n上海证券交易所','H 股： \n上海证券交易所'),
    (89,'中华人民共和国财政部颁布的企业会计准\n则','国际财务报告会计准则'),
    (99,'母公司股东的净利润 \n \n31,809 \n50,313','母公司股东的净利润 \n \n'),
])
def test_wrong_identity_accounting_basis_and_missing_profit_cells_do_not_fall_back(page,old,new):
    sample = deepcopy(SAMPLE)
    _replace(sample,page,old,new)
    _assert_no_accepted_amounts(_candidate(sample))


@pytest.mark.parametrize('company',[build_company_identity('600028','另一家公司'),
                                    build_company_identity('600019','宝钢股份')])
def test_exact_verified_source_with_wrong_company_identity_is_never_routed_to_generic(company):
    _assert_no_accepted_amounts(_candidate(company=company),company)


@pytest.mark.parametrize('year',[2024,2026])
def test_unsupported_year_remains_closed_even_with_usable_original_tables(year):
    sample = deepcopy(SAMPLE)
    sample['year'] = year
    _assert_no_accepted_amounts(_candidate(sample))


def test_generic_success_cannot_fill_any_amount_after_cas_failure(monkeypatch):
    generic = dict(unit='人民币百万元',page_number=175,end_page_number=175)
    for key in SAMPLE['expected']:
        generic['current_'+key] = 999999
        generic['previous_'+key] = 888888
    for function in ('find_income_statement_figures','find_balance_sheet_figures','find_cash_flow_figures'):
        monkeypatch.setattr('src.audited_company_onboarding.'+function,
                            lambda *args, **kw: deepcopy(generic))
    def forbidden(*args,**kw):
        raise AssertionError('A recognized Sinopec report must not use generic reconciliation')
    monkeypatch.setattr('src.audited_company_onboarding.check_general_income_reconciliation',forbidden)
    sample = deepcopy(SAMPLE)
    sample['pages'] = [p for p in sample['pages'] if p['page_number'] != 99]
    _assert_no_accepted_amounts(_candidate(sample))


def test_non_cas_donor_values_cannot_override_valid_cas_metrics():
    sample = deepcopy(SAMPLE)
    _replace(sample,101,'35,633','999,999')
    _replace(sample,175,'32,476','888,888')
    _replace(sample,180,'162,496','777,777')
    candidate = _candidate(sample)
    assert candidate['status'] == 'ready_for_human_review'
    for key, expected in SAMPLE['expected'].items():
        assert [candidate['values']['current_'+key],candidate['values']['previous_'+key]] == expected
