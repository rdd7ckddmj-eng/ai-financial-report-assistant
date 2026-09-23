"""New issuer profiles must preserve identity, scope and human-review gates."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path

import pytest

from src.china_stock import CMOC_2025_REPORT_URL, build_company_identity, is_allowed_disclosure_url
from src.manual_financial_snapshot import build_manual_financial_snapshot
from src.financial_snapshot_review import build_financial_snapshot_review, build_exportable_review_workpaper, FinancialSnapshotReviewError
from src.on_demand_financial_snapshot import build_financial_snapshot_report_html

FIXTURES = Path(__file__).parent / 'fixtures'
CMOC = json.loads((FIXTURES / 'cmoc_2025_cas_traditional.json').read_text())
CITIC = json.loads((FIXTURES / 'citic_securities_2024_2025.json').read_text())


def manual(monkeypatch, sample, company=None):
    monkeypatch.setattr('src.manual_financial_snapshot.extract_pdf_pages', lambda *a, **kw: deepcopy(sample['pages']))
    return build_manual_financial_snapshot(
        company or build_company_identity(sample['code'], sample['name']), b'%PDF-test-fixture-only',
        report_year=sample['year'], source_url=sample['source_url'], published_date=sample['published_date'],
        identity_confirmed=True, today=date(2026, 9, 24))


@pytest.mark.parametrize('sample', [CMOC] + CITIC, ids=['cmoc-2025', 'citic-2024', 'citic-2025'])
def test_production_integration_keeps_evidence_and_human_review_pending(monkeypatch, sample):
    snapshot = manual(monkeypatch, sample)
    assert snapshot['status'] == 'ready_for_human_review'
    assert '银行利润表' not in json.dumps(snapshot, ensure_ascii=False)
    assert all(v for v in snapshot['statement_checks'].values())
    for metric in snapshot['metrics']:
        assert metric['current_yuan'] is not None and metric['previous_yuan'] is not None
        assert metric['source']['excerpt']
    profit = next(m for m in snapshot['metrics'] if m['key'] == 'net_profit')
    assert '归母净利润' in profit['source']['accounting_basis']
    if sample['code'] == '600030':
        assert all(value is None for value in snapshot['ratios'].values())
    html = build_financial_snapshot_report_html(snapshot)
    assert '资产负债与现金流金额关系' in html
    review = build_financial_snapshot_review(snapshot)
    assert all(m['decision'] == 'pending' for m in review['metrics'])
    with pytest.raises(FinancialSnapshotReviewError):
        build_exportable_review_workpaper(review)


@pytest.mark.parametrize('url', [
    CMOC_2025_REPORT_URL + '?replacement=1',
    CMOC_2025_REPORT_URL.replace('1683_c.pdf', '1684_c.pdf'),
    CMOC_2025_REPORT_URL.replace('www.hkexnews.hk', 'mirror.hkexnews.hk'),
    CMOC_2025_REPORT_URL.replace('https:', 'http:'),
])
def test_official_hkex_exception_is_only_the_verified_original(url):
    assert is_allowed_disclosure_url(CMOC_2025_REPORT_URL)
    assert not is_allowed_disclosure_url(url)


@pytest.mark.parametrize('sample', [CMOC] + CITIC)
def test_wrong_issuer_identity_never_borrows_known_statement_amounts(monkeypatch, sample):
    company = build_company_identity(sample['code'], '另一家公司')
    with pytest.raises(ValueError):
        manual(monkeypatch, sample, company)


def test_cmoc_original_does_not_grant_other_company_or_year_access(monkeypatch):
    with pytest.raises(ValueError):
        manual(monkeypatch, CMOC, build_company_identity('601319', '中国人保'))
    sample = deepcopy(CMOC)
    sample['year'] = 2024
    with pytest.raises(ValueError):
        manual(monkeypatch, sample)


@pytest.mark.parametrize('sample', [CMOC] + CITIC)
def test_missing_statement_does_not_fall_back_to_generic_amounts(monkeypatch, sample):
    sample = deepcopy(sample)
    needle = '合併利潤表' if sample['code'] == '603993' else '合并利润表'
    sample['pages'] = [p for p in sample['pages'] if needle not in p['text']]
    snapshot = manual(monkeypatch, sample)
    assert snapshot['status'] == 'needs_review'
    assert all(m['current_yuan'] is None and m['previous_yuan'] is None for m in snapshot['metrics'])
