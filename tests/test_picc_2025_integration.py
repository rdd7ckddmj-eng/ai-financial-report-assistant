"""The text-based CAS original supplements, never replaces, PICC's negative PDF."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path

import pytest

from src.china_stock import PICC_2025_REPORT_URL, build_company_identity, is_allowed_disclosure_url
from src.insurance_group_statement_extractor import (
    extract_insurance_group_statements, is_picc_2025_annual_report_identity, _lines,
)
from src.manual_financial_snapshot import build_manual_financial_snapshot
from src.financial_snapshot_review import (
    build_financial_snapshot_review, build_exportable_review_workpaper, FinancialSnapshotReviewError,
)

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/picc_insurance_2025_statements.json').read_text())
COMPANY = build_company_identity('601319', '中国人保')


def report_pages():
    return sorted(deepcopy(FIXTURE['identity_pages'] + FIXTURE['pages']))


def manual(monkeypatch, pages=None, company=None, year=2025):
    pages = report_pages() if pages is None else pages
    monkeypatch.setattr('src.manual_financial_snapshot.extract_pdf_pages',
        lambda *a, **kw: [dict(page_number=n, text=t) for n, t in pages])
    return build_manual_financial_snapshot(company or COMPANY, b'%PDF-fixture-only',
        report_year=year, source_url=PICC_2025_REPORT_URL, published_date='2026-03-26',
        identity_confirmed=True, today=date(2026, 9, 24))


def test_real_text_version_passes_production_evidence_and_keeps_review_pending(monkeypatch):
    assert is_picc_2025_annual_report_identity(COMPANY, report_pages(), 2025)
    snapshot = manual(monkeypatch)
    assert snapshot['status'] == 'ready_for_human_review'
    assert snapshot['report']['statement_template'] == 'insurance_picc_million_v1'
    assert all(snapshot['statement_checks'].values())
    expected = {
        'revenue': (669044000000, 621972000000, 131),
        'net_profit': (46646000000, 42869000000, 132),
        'operating_cash_flow': (118689000000, 87990000000, 137),
        'total_assets': (2027683000000, 1766384000000, 128),
        'total_liabilities': (1607494000000, 1399158000000, 129),
    }
    for metric in snapshot['metrics']:
        current, prior, page = expected[metric['key']]
        assert metric['current_yuan'] == current
        assert metric['previous_yuan'] == prior
        assert str(page) in str(metric['source']['pages'])
        assert metric['source']['excerpt_status'] == 'captured'
        assert metric['source']['excerpt']
    assert snapshot['metrics'][0]['label'] == '营业总收入（保险报表）'
    assert all(value is None for value in snapshot['ratios'].values())
    review = build_financial_snapshot_review(snapshot)
    assert all(metric['decision'] == 'pending' for metric in review['metrics'])
    with pytest.raises(FinancialSnapshotReviewError):
        build_exportable_review_workpaper(review)


@pytest.mark.parametrize('change', ['code', 'name', 'year', 'legal_name', 'stock_code', 'title', 'summary', 'cas_missing', 'ifrs'])
def test_wrong_identity_or_accounting_basis_cannot_use_the_exact_hkex_url(monkeypatch, change):
    pages = report_pages(); company = dict(COMPANY); year = 2025
    if change == 'code': company = build_company_identity('601601', '中国太保')
    if change == 'name': company['name'] = '另一家公司'
    if change == 'year': year = 2024
    replacements = {
        'legal_name': ('中国人民保险集团股份有限公司', '中国人民财产保险股份有限公司'),
        'stock_code': ('601319', '601318'),
        'title': ('二零二五年', '二零二四年'),
        'cas_missing': ('本财务报表按照财政部颁布的企业会计准则', '本财务报表按照未核实的会计准则'),
        'ifrs': ('本财务报表按照财政部颁布的企业会计准则', '本财务报表按照国际财务报告会计准则'),
    }
    if change in replacements:
        old, new = replacements[change]
        # Name/title glyphs are occasionally split by whitespace in the PDF.
        # Mutate their normalized identity text, keeping financial pages intact.
        pages = [(n, (''.join(t.split()) if n <= 10 else t).replace(old, new)) for n, t in pages]
        if change == 'title':
            pages = [(n, t.replace('2025年年度报告', '2024年年度报告')) for n, t in pages]
    if change == 'summary': pages[1] = (pages[1][0], pages[1][1] + '\n2025年年度报告摘要')
    assert not is_picc_2025_annual_report_identity(company, pages, year)
    with pytest.raises(ValueError):
        manual(monkeypatch, pages, company, year)


@pytest.mark.parametrize('url', [
    PICC_2025_REPORT_URL + '?replacement=1',
    PICC_2025_REPORT_URL + '#replacement',
    PICC_2025_REPORT_URL.replace('1780_c.pdf', '1782_c.pdf'),
    PICC_2025_REPORT_URL.replace('www.hkexnews.hk', 'www1.hkexnews.hk'),
    PICC_2025_REPORT_URL.replace('https:', 'http:'),
    'https://www.hkexnews.hk/listedco/listconews/sehk/2026/0428/2026042800675_c.pdf',
])
def test_only_individually_verified_cas_url_is_allowed(url):
    assert is_allowed_disclosure_url(PICC_2025_REPORT_URL)
    assert not is_allowed_disclosure_url(url)


def test_original_outline_numbered_version_is_still_needs_review(monkeypatch):
    original = json.loads((Path(__file__).parent / 'fixtures/picc_insurance_2025_numeric_text_missing.json').read_text())
    # Even with good identity evidence, missing numeric report text stays empty.
    snapshot = manual(monkeypatch, sorted(FIXTURE['identity_pages'] + original['pages']))
    assert snapshot['status'] == 'needs_review'
    assert snapshot['report']['statement_template'] == 'insurance_unsupported_v1'
    assert all(m['current_yuan'] is None and m['previous_yuan'] is None for m in snapshot['metrics'])


@pytest.mark.parametrize('source_url', [
    PICC_2025_REPORT_URL,
    'https://static.cninfo.com.cn/finalpage/2026-03-27/1225037867.PDF',
])
@pytest.mark.parametrize('change', ['none', 'missing_cas', 'ifrs', 'missing_front', 'stock_code', 'title'])
def test_all_candidate_paths_require_complete_picc_2025_cas_identity(source_url, change):
    from src.audited_company_onboarding import build_candidate_report_result
    from src.on_demand_financial_snapshot import build_on_demand_financial_snapshot
    pages = report_pages()
    if change == 'missing_cas':
        pages = [(n, t) for n, t in pages if n != 141]
    elif change == 'ifrs':
        pages = [(n, t.replace('本财务报表按照财政部颁布的企业会计准则',
                              '本财务报表按照国际财务报告会计准则')) for n, t in pages]
    elif change == 'missing_front':
        pages = [(n, t) for n, t in pages if n > 10]
    elif change == 'stock_code':
        pages = [(n, t.replace('601319', '601318')) for n, t in pages]
    elif change == 'title':
        pages = [(n, ''.join(t.split()).replace('二零二五年', '二零二四年')
                  .replace('2025年年度报告', '2024年年度报告') if n <= 10 else t) for n, t in pages]
    candidate = build_candidate_report_result(COMPANY,
        dict(report_year=2025, title='2025年年度报告', published_date='2026-03-26', url=source_url),
        b'%PDF-fixture-only', [dict(page_number=n, text=t) for n, t in pages])
    snapshot = build_on_demand_financial_snapshot(COMPANY, candidate)
    if change == 'none':
        assert candidate['status'] == snapshot['status'] == 'ready_for_human_review'
        assert candidate['statement_template'] == 'insurance_picc_million_v1'
    else:
        assert candidate['status'] == snapshot['status'] == 'needs_review'
        assert candidate['statement_template'] == 'insurance_unsupported_v1'
        assert all(value is None for value in candidate['values'].values())
        assert all(m['current_yuan'] is None and m['previous_yuan'] is None for m in snapshot['metrics'])


@pytest.mark.parametrize('label,values', [
    ('保险服务收入\n34', ('570,717', '537,709')),
    ('保险服务费用', ('527,170', '492,837')),
    ('三、营业利润', ('74,937', '70,644')),
    ('四、利润总额', ('74,506', '70,618')),
    ('五、净利润', ('63,033', '57,820')),
    ('归属于母公司股东的净利润', ('46,646', '42,869')),
    ('资产总计', ('2,027,683', '1,766,384')),
    ('负债和股东权益总计', ('2,027,683', '1,766,384')),
    ('股东权益合计', ('420,189', '367,226')),
    ('经营活动产生的现金流量净额\n48(1)', ('118,689', '87,990')),
    ('投资活动使用的现金流量净额', ('(155,744)', '(77,599)')),
    ('筹资活动产生的现金流量净额', ('53,385', '4,860')),
    ('五、现金及现金等价物净增加额\n48(2)', ('15,742', '15,297')),
    ('六、年末现金及现金等价物余额\n49', ('59,874', '44,132')),
])
@pytest.mark.parametrize('column', [0, 1], ids=['current', 'comparative'])
def test_every_existing_two_period_reconciliation_is_still_enforced(label, values, column):
    pages = [(n, '\n'.join(_lines(t))) for n, t in FIXTURE['pages']]
    old = label + '\n' + '\n'.join(values)
    changed = list(values); changed[column] = '999,999'
    new = label + '\n' + '\n'.join(changed)
    assert sum(t.count(old) for _, t in pages) == 1
    pages = [(n, t.replace(old, new)) for n, t in pages]
    assert extract_insurance_group_statements(pages, 2025, '601319') is None


@pytest.mark.parametrize('current,old', [
    ('公允价值变动收益', '公允价值变动损益'),
    ('汇兑损益', '汇兑收益'),
    ('提取/(转回)保费准备金', '转回提取保费准备金'),
    ('信用减值损失/(转回)', '信用减值(转回)/损失'),
    ('归属于母公司股东的净利润', '1.归属于母公司股东的净利润'),
    ('三、筹资活动产生的现金流量', '三、筹资活动产生/(使用)的现金流量'),
    ('五、现金及现金等价物净增加额', '五、现金及现金等价物净增加/(减少)额'),
])
def test_year_specific_labels_are_not_silently_aliases(current, old):
    pages = [(n, '\n'.join(_lines(t))) for n, t in FIXTURE['pages']]
    assert any(current in t for _, t in pages)
    pages = [(n, t.replace(current, old)) for n, t in pages]
    assert extract_insurance_group_statements(pages, 2025, '601319') is None
