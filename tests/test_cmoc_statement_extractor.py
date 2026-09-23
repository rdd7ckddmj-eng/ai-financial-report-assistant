"""Actual CMOC text, plus destructive column/row/scope counterexamples."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from src.cmoc_statement_extractor import (
    CMOC_TEMPLATE, extract_cmoc_statements, is_cmoc_annual_report_identity,
)

FIXTURES = Path(__file__).parent/'fixtures'
SAMPLE = json.loads((FIXTURES/'cmoc_2025_cas_traditional.json').read_text())


def source():
    return [(p['page_number'],p['text']) for p in SAMPLE['pages']]


def mutate(page, old, new, count=1):
    pages=source()
    for i,(n,t) in enumerate(pages):
        if n==page:
            assert old in t
            pages[i]=(n,t.replace(old,new,count))
    return pages


def test_actual_report_all_five_metrics_both_periods_with_original_evidence():
    pages=source();before=deepcopy(pages)
    assert is_cmoc_annual_report_identity(dict(code='603993',name='洛阳钼业'),pages,2025)
    result=extract_cmoc_statements(pages,2025)
    assert pages==before
    assert result['template']==CMOC_TEMPLATE
    assert result['income_reconciliation']['status']=='passed'
    assert {k:len(v) for k,v in result['statement_reconciliation'].items()}==dict(income=7,balance=10,cash=11)
    assert all(c['passed'] for section in result['statement_reconciliation'].values() for c in section)
    for field,expected in SAMPLE['expected'].items():
        section='income' if field in ('revenue','net_profit') else 'cash' if field=='operating_cash_flow' else 'balance'
        assert [result[section]['current_'+field],result[section]['previous_'+field]]==expected
        assert result[section]['unit']=='元' and result[section]['original_unit']=='人民幣元'
    assert '營業收入' in result['income']['metric_sources']['revenue']['excerpt']
    assert '合併及母公司資產負債表' in result['audit_evidence']['excerpt'].replace('\n','')
    assert result['audit_evidence']['page']==84 and result['audit_evidence']['basis_page']==104


@pytest.mark.parametrize('damage', [
    (93,'2025年度\n2024年度','2024年度\n2025年度'),
    (93,'2025年度\n2024年度','2025年度\n2024年度\n2023年度'),
    (88,'人民幣元','人民幣千元'),
    (89,'附註\n','附註\n美元元\n'),
    (96,'本年金額\n上年金額','上年金額\n本年金額'),
    (93,'206,683,649,050.43\n213,028,664,834.79','206,683,649,050.43'),
    (93,'206,683,649,050.43','206,,683,649,050.43'),
    (93,'206,683,649,050.43','206,683,649,050.43\n777.77'),
    (93,'206,683,649,050.43','206,683,649,050.43\n不適用'),
    (93,'（五）48','（五）49'),
    (93,'1.歸屬於母公司股東的淨利潤','1.歸屬於母公司股東的綜合收益'),
    (93,'20,338,750,797.53','20,338,750,798.53'),
    (93,'(7,688,124,922.01)','7,688,124,922.01'),
    (93,'(7,688,124,922.01)','(7,688,124,922.01'),
    (88,'90,584,337,060.81','90,584,337,061.81'),
    (88,'7,053,870,748.59','7,053,870,747.59'),
    (89,'101,145,637,570.27','101,145,637,570.27\n0.00'),
    (97,'30,682,025,424.15','30,682,025,424.16\n777,,777'),
    (97,'(8,497,206,728.55)','8,497,206,728.55'),
    (97,'本財務報表由下列負責人簽署：','未知項目\n本財務報表由下列負責人簽署：'),
    (93,'合併利潤表','公司利潤表'),
    (95,'公司利潤表','合併利潤表'),
    (98,'母公司現金流量表','現金流量表'),
    (104,'財政部頒佈的企業會計準則','國際財務報告會計準則'),
    (84,'2025年度的合併及母公司利潤表','2024年度的合併及母公司利潤表'),
    (87,'2026年3月27日','2025年3月27日'),
])
def test_missing_damaged_or_wrong_scope_evidence_never_releases_amounts(damage):
    result=extract_cmoc_statements(mutate(*damage),2025)
    assert result is not None
    assert result['income'] is result['balance'] is result['cash'] is None
    assert result['income_reconciliation']['status'] in ('missing_evidence','mismatch')
    assert result['failure_reason']


@pytest.mark.parametrize('damage', ['cover_code','cover_year','cover_summary','duplicate_page','page_gap','duplicate_row','missing_owner','missing_basis','missing_audit'])
def test_identity_and_document_boundaries(damage):
    pages=source()
    if damage=='cover_code':pages=mutate(1,'603993.SH','601319.SH')
    if damage=='cover_year':pages=mutate(1,'2025年度報告','2024年度報告')
    if damage=='cover_summary':pages=mutate(1,'2025年度報告','2025年度報告摘要')
    if damage=='duplicate_page':pages.append(pages[-1])
    if damage=='page_gap':pages=[(n+1 if n==89 else n,t) for n,t in pages]
    if damage=='duplicate_row':pages=mutate(93,'其中：營業收入','其中：營業收入\n其中：營業收入')
    if damage=='missing_owner':
        pages=mutate(93,'1.歸屬於母公司股東的淨利潤\n  （淨虧損以「-」號填列）\n20,338,750,797.53\n13,532,035,002.94\n','')
    if damage=='missing_basis':pages=[(n,t) for n,t in pages if n!=104]
    if damage=='missing_audit':pages=[(n,t) for n,t in pages if n!=84]
    result=extract_cmoc_statements(pages,2025)
    if damage.startswith('cover_'):assert result is None
    else:assert result is not None and result['income'] is result['balance'] is result['cash'] is None


def test_old_a_share_image_pdf_and_other_years_are_not_upgraded():
    old=json.loads((FIXTURES/'cmoc_2025_image_negative.json').read_text())
    pages=[(p['page_number'],p['text']) for p in old['pages']]
    assert extract_cmoc_statements(pages,2025) is None
    assert extract_cmoc_statements(source(),2024) is None
    assert not is_cmoc_annual_report_identity(dict(code='601319',name='中国人保'),source(),2025)


def test_shared_candidate_preserves_traditional_source_and_requires_human_review():
    from src.audited_company_onboarding import build_candidate_report_result
    from src.china_stock import build_company_identity
    from src.on_demand_financial_snapshot import build_on_demand_financial_snapshot
    from src.financial_snapshot_review import build_financial_snapshot_review
    report=dict(report_year=2025,title='洛阳钼业2025年度报告',url=SAMPLE['source_url'],published_date=SAMPLE['published_date'])
    candidate=build_candidate_report_result(build_company_identity('603993','洛阳钼业'),report,b'%PDF-fixture-only',SAMPLE['pages'])
    snapshot=build_on_demand_financial_snapshot(build_company_identity('603993','洛阳钼业'),candidate)
    assert snapshot['status']=='ready_for_human_review'
    for metric in snapshot['metrics']:
        assert [metric['current_yuan'],metric['previous_yuan']]==SAMPLE['expected'][metric['key']]
        assert metric['source']['accounting_basis']==('归母净利润（合并报表；繁体原文；中国企业会计准则）' if metric['key']=='net_profit' else '合并口径（繁体原文；中国企业会计准则）')
        assert metric['source']['excerpt_status']=='captured'
    assert '營業收入' in snapshot['metrics'][0]['source']['excerpt']
    assert all(m['decision']=='pending' for m in build_financial_snapshot_review(snapshot)['metrics'])


@pytest.mark.parametrize('damage',[(104,'財政部頒佈的企業會計準則','國際財務報告會計準則'),(93,'合併利潤表','公司利潤表')])
def test_shared_candidate_does_not_fallback_after_cmoc_profile_failure(damage):
    from src.audited_company_onboarding import build_candidate_report_result
    from src.china_stock import build_company_identity
    company=build_company_identity('603993','洛阳钼业')
    pages=[dict(page_number=n,text=t) for n,t in mutate(*damage)]
    result=build_candidate_report_result(company,dict(report_year=2025,title='洛阳钼业2025年度报告',url=SAMPLE['source_url'],published_date=SAMPLE['published_date']),b'%PDF-fixture-only',pages)
    assert result['status']=='needs_review'
    assert result['statement_template']==CMOC_TEMPLATE
    assert not result['statement_checks']['income_statement_reconciled']


@pytest.mark.parametrize('column',[0,1])
def test_receivable_children_sum_cannot_exceed_other_receivables(column):
    pages=source()
    numbers=[('338,482,419.43','32,000,000.00','4,447,817,510.24'),
             ('277,967,881.17','210,000,000.00','4,143,648,410.54')]
    interest,dividend,large=numbers[column]
    pages=[(n,t.replace(interest,large).replace(dividend,large) if n==88 else t) for n,t in pages]
    result=extract_cmoc_statements(pages,2025)
    assert result['income'] is result['balance'] is result['cash'] is None
    assert '应收利息与应收股利合计超过其他应收款' in result['failure_reason']
