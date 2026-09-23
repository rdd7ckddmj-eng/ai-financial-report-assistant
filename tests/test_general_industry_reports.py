"""Regression evidence from eight complete official 2025 reports.

Fixtures contain unchanged statement-page text, not complete PDFs. Separate
batch receipts run the actual complete PDFs through the production upload path.
"""
import json
from pathlib import Path
import pytest
from src.audited_company_onboarding import build_candidate_report_result
from src.china_stock import build_company_identity
from src.on_demand_financial_snapshot import build_on_demand_financial_snapshot
from src.financial_statement_extractor import find_income_statement_figures, _extract_chinese_row_pair
from src.statement_evidence_rules import extract_statement_unit, inherit_statement_units

SAMPLES=json.loads((Path(__file__).parent/'fixtures/general_industry_2025_statements.json').read_text())

@pytest.mark.parametrize('sample',SAMPLES,ids=lambda s:s['code'])
def test_real_industry_pages_keep_both_year_amounts_and_sources(sample):
    company=build_company_identity(sample['code'],sample['name'])
    report=dict(report_year=sample['year'],title=f"{sample['name']}2025年年度报告",
        url=sample['source_url'],published_date=sample['published_date'])
    candidate=build_candidate_report_result(company,report,b'%PDF-page-fixture',sample['pages'])
    snapshot=build_on_demand_financial_snapshot(company,candidate)
    assert snapshot['status']=='ready_for_human_review'
    for metric in snapshot['metrics']:
        expected=sample['expected'][metric['key']]
        assert metric['current_yuan']==expected['current_yuan']
        assert metric['previous_yuan']==expected['previous_yuan']
        assert metric['pages']==expected['pages']
        assert metric['source']['excerpt_status']=='captured'


def test_boe_total_profit_cannot_replace_attributable_profit_on_next_page():
    sample=next(s for s in SAMPLES if s['code']=='000725')
    first=next(p for p in sample['pages'] if p['page_number']==100)
    second=next(p for p in sample['pages'] if p['page_number']==101)
    assert find_income_statement_figures([(100,first['text'])]) is None
    found=find_income_statement_figures([(100,first['text']),(101,second['text'])])
    assert found['current_net_profit']==sample['expected']['net_profit']['current_yuan']
    assert found['current_net_profit']!=5_027_373_569
    assert find_income_statement_figures([(100,first['text']),(102,second['text'])]) is None


def test_parent_revenue_must_not_override_consolidated_revenue_on_shared_page():
    p1='合并利润表\n单位：元\n一、营业总收入 1000 800\n净利润 120 100'
    p2='归属于母公司股东的净利润 110 90\n母公司利润表\n一、营业收入 100 80'
    found=find_income_statement_figures([(10,p1),(11,p2)])
    assert (found['current_revenue'],found['current_net_profit'])==(1000,110)
    assert find_income_statement_figures([(10,p1),(11,p2.replace('归属于母公司股东的净利润 110 90',''))]) is None


@pytest.mark.parametrize('note',['(五)45','（五）45','(五)59(1)'])
def test_supported_note_references_do_not_shift_amounts(note):
    assert _extract_chinese_row_pair(['营业收入',note,'100','80'],('营业收入',))==(100,80)


@pytest.mark.parametrize('note',['(五)45x','(五45','（五)45','(五)59(1','附注不明'])
def test_malformed_note_does_not_borrow_following_values(note):
    assert _extract_chinese_row_pair(['营业收入',note,'100','80'],('营业收入',)) is None


@pytest.mark.parametrize('unit',['人民币万元','美元','港元'])
@pytest.mark.parametrize('layout',['adjacent','continuation','explicit'])
def test_conflicting_units_fail_even_on_long_continuation_headers(unit,layout):
    lines=['合并利润表','2025年度','人民币元']
    if layout=='continuation':lines+=['营业收入 100 80']+['其他科目']*20+['合并利润表（续）','2025年度']
    lines += [('单位：'+unit) if layout=='explicit' else unit]
    assert extract_statement_unit(lines)==''


def test_unit_cannot_be_borrowed_from_account_or_parent_header():
    assert extract_statement_unit(['合并利润表','营业收入','人民币元'])==''
    assert extract_statement_unit(['母公司利润表','人民币元'])==''


def test_conflicting_standalone_unit_cannot_be_revived_by_section_inheritance():
    pages=[(10,'二、财务报表\n财务附注中报表的单位为：千元\n合并资产负债表'),
        (11,'合并利润表\n人民币千元\n人民币万元\n营业收入 100 80'),
        (12,'合并现金流量表\n单位：千元')]
    statements=[dict(page_number=p,end_page_number=p,unit=u) for p,u in [(10,'千元'),(11,''),(12,'千元')]]
    inherit_statement_units(pages,statements)
    assert all(s['unit']=='' for s in statements)
