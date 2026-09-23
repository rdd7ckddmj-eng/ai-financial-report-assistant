"""CMS source-page fixtures through production routing; full PDFs checked separately."""
from datetime import date
import json
from pathlib import Path

import pytest

from src.audited_company_onboarding import build_candidate_report_result
from src.china_stock import build_company_identity
from src.manual_financial_snapshot import build_manual_financial_snapshot
from src.on_demand_financial_snapshot import build_on_demand_financial_snapshot
from src.public_financial_history import build_public_financial_history
from src.public_financial_reconciliation import build_public_financial_reconciliation
from src.securities_statement_extractor import CMS_SECURITIES_TEMPLATE


def fixture(year=2025):
    data=json.loads((Path(__file__).parent/'fixtures'/f'cms_securities_{year}_statements.json').read_text())
    texts=dict(data['pages'])
    # Blank unneeded fixture pages preserve actual physical offsets and prevent
    # the first-ten-pages check from accidentally seeing a later statement.
    pages=[dict(page_number=n,text=texts.get(n,'')) for n in range(1,data['pdf_page_count']+1)]
    return data,pages


def arguments(year=2025):
    data,_=fixture(year)
    return dict(report_year=year,source_url=data['source_url'],published_date=f'{year+1}-03-28',
                identity_confirmed=True,today=date(2026,9,23))


def snapshot(monkeypatch,year=2025,pages=None,company=None,**changes):
    if pages is None:_,pages=fixture(year)
    monkeypatch.setattr('src.manual_financial_snapshot.extract_pdf_pages',lambda *_a,**_k:pages)
    options=arguments(year);options.update(changes)
    return build_manual_financial_snapshot(company or build_company_identity('600999','招商证券'),
        b'%PDF-CMS-source-pages-test-fixture',**options)


@pytest.mark.parametrize('year',[2024,2025])
def test_cms_real_identity_pages_enable_complete_route_without_ordinary_ratios(monkeypatch,year):
    result=snapshot(monkeypatch,year)
    assert result['status']=='ready_for_human_review'
    assert result['report']['statement_template']==CMS_SECURITIES_TEMPLATE
    assert result['report']['page_count']==(282 if year==2024 else 281)
    assert all(result['statement_checks'].values())
    assert result['metrics'][0]['label']=='营业总收入（证券报表）'
    assert all(m['source']['excerpt_status']=='captured' for m in result['metrics'])
    assert all(m['current_yuan'] is not None for m in result['metrics'])
    assert all(v is None for v in result['ratios'].values())
    assert result['input_provenance']=='user_uploaded_official_report_candidate'


@pytest.mark.parametrize('change',[
    'wrong_company','wrong_name','wrong_year','replace_legal_name','subsidiary_name_field',
    'summary','missing_identity','wrong_a_share_code',
])
def test_cms_manual_entry_rejects_incorrect_or_partial_report_identity(monkeypatch,change):
    _,pages=fixture();company=build_company_identity('600999','招商证券');options={}
    if change=='wrong_company':company=build_company_identity('600030','中信证券')
    if change=='wrong_name':company=build_company_identity('600999','中信证券')
    if change=='wrong_year':options['report_year']=2024
    if change=='replace_legal_name':
        pages[14]['text']=pages[14]['text'].replace('招商证券股份有限公司','中信证券股份有限公司')
    if change=='subsidiary_name_field':
        pages[14]['text']=pages[14]['text'].replace('公司的中文名称','控股子公司的中文名称')
    if change=='summary':pages[0]['text']='招商证券股份有限公司2025年年度报告摘要'
    if change=='missing_identity':
        for page in pages[:16]:page['text']=''
    if change=='wrong_a_share_code':
        for page in pages[:16]:page['text']=page['text'].replace('600999','600998')
    with pytest.raises(ValueError):snapshot(monkeypatch,pages=pages,company=company,**options)


@pytest.mark.parametrize('code,name',[('600999','招商证券'),('600999','待核验公司'),('601688','华泰证券')])
def test_known_broker_missing_identity_never_falls_back_to_ordinary_candidate(code,name):
    _,pages=fixture()
    for page in pages[:16]:page['text']=''
    company=build_company_identity(code,name)
    report=dict(report_year=2025,title='2025年年度报告',published_date='2026-03-28',url=arguments()['source_url'])
    candidate=build_candidate_report_result(company,report,b'%PDF-test-source-pages',pages)
    result=build_on_demand_financial_snapshot(company,candidate)
    assert result['report']['statement_template']=='securities_unsupported_v1'
    assert result['status']=='needs_review'
    assert not any(result['statement_checks'].values())
    assert all(m['current_yuan'] is None for m in result['metrics'])
    assert all(v is None for v in result['ratios'].values())


@pytest.mark.parametrize('org,has_total,status',[
    ('证券',True,'amount_close'),('证券',False,'not_comparable'),('通用',True,'not_comparable'),
])
def test_cms_public_comparison_uses_explicit_securities_total_revenue(monkeypatch,org,has_total,status):
    candidate=snapshot(monkeypatch)
    amounts={m['key']:m['current_yuan'] for m in candidate['metrics']}
    public_row=dict(SECUCODE='600999.SH',SECURITY_CODE='600999',SECURITY_NAME_ABBR='招商证券',
        ORG_TYPE=org,REPORT_DATE='2025-12-31',REPORT_TYPE='年报',NOTICE_DATE='2026-03-28',
        UPDATE_DATE='2026-03-28',CURRENCY='CNY',OPERATE_INCOME_PK=777,
        TOTALOPERATEREVE=amounts['revenue'] if has_total else None,
        PARENTNETPROFIT=amounts['net_profit'],NETCASH_OPERATE_PK=amounts['operating_cash_flow'],
        TOTAL_ASSETS_PK=amounts['total_assets'],LIABILITY=amounts['total_liabilities'],
        TOTAL_EQUITY_PK=amounts['total_assets']-amounts['total_liabilities'])
    public=build_public_financial_history(candidate['company'],[public_row],fetched_at='2026-09-23T01:00:00+00:00')
    result=build_public_financial_reconciliation(public,candidate)
    revenue=next(r for r in result['rows'] if r['key']=='revenue')
    assert revenue['status']==status
    assert revenue['public_field']=='total_operating_revenue'
    assert revenue['public_yuan']==(amounts['revenue'] if has_total else None)
    assert result['status']=='pending_human_review'


def test_cms_review_export_and_research_case_preserve_financial_ratio_exclusion(monkeypatch):
    # In-memory fixture simulation only; no human confirmation or real case save.
    from src.financial_snapshot_review import (build_financial_snapshot_review,
        confirm_snapshot_metric,build_exportable_review_workpaper,CORE_METRIC_KEYS)
    from src.research_case_financial_review_bridge import (_validate_workpaper,
        build_financial_review_research_case_patch)
    from src.research_case import new_research_case,apply_case_patch
    candidate=snapshot(monkeypatch)
    review=build_financial_snapshot_review(candidate)
    for key in CORE_METRIC_KEYS:review=confirm_snapshot_metric(review,key)
    workpaper=build_exportable_review_workpaper(review)
    assert all(v is None for v in workpaper['ratios'].values())
    case=new_research_case('cms-fixture-only',candidate['company'],mode='current',as_of_date=None,
        effective_market_date='2026-09-23',created_at='2026-09-23T01:00:00+00:00')
    clean=_validate_workpaper(case,workpaper)
    assert clean['report']['statement_template']==CMS_SECURITIES_TEMPLATE
    patch=build_financial_review_research_case_patch(case,workpaper,patch_id='cms-fixture-write',emitted_at=workpaper['exported_at'])
    updated=apply_case_patch(case,patch)
    assert '金融机构模板不计算普通公司比例' in json.dumps(updated,ensure_ascii=False)
