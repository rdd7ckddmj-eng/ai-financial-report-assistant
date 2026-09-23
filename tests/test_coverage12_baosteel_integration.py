"""Actual Baosteel income-page recovery through reconciliation and source UI.

Only unrelated balance/cash extractors are stubbed in focused snapshot tests;
these tests do not claim to re-test the full three-statement original PDF.
"""
from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
import html as html_lib
import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.audited_company_onboarding import build_candidate_report_result
from src.china_stock import build_company_identity
from src.financial_snapshot_review import (
    CORE_METRIC_KEYS, FinancialSnapshotReviewError,
    build_exportable_review_workpaper, build_financial_snapshot_review,
    confirm_snapshot_metric, serialise_review_workpaper,
)
from src.financial_statement_extractor import find_income_statement_figures
from src.general_income_reconciliation import check_general_income_reconciliation
from src.on_demand_financial_snapshot import (
    build_financial_snapshot_report_html, build_on_demand_financial_snapshot,
)

SAMPLE = json.loads((Path(__file__).parent / 'fixtures/baosteel_attributable_crosspage_2025.json').read_text())
COMPANY = build_company_identity('600019','宝钢股份')
SOURCE_URL = 'https://static.cninfo.com.cn/finalpage/2026-04-30/1225257227.PDF'
PDF = b'%PDF-fixture-only-not-original'


def pages():
    return [(p['page_number'],p['text']) for p in SAMPLE['pages']]


def replace(source,page,old,new):
    source=list(source)
    i=next(i for i,(n,_) in enumerate(source) if n==page)
    assert old in source[i][1]
    source[i]=(page,source[i][1].replace(old,new,1))
    return source


def checked(source,*,year=2025):
    figures=find_income_statement_figures(source)
    return figures,check_general_income_reconciliation(source,figures,report_year=year)


def candidate(monkeypatch,source=None):
    # Isolate income recovery, provenance and review-gate integration. Other
    # statement parsers have their own fixtures and complete-PDF regression run.
    monkeypatch.setattr('src.audited_company_onboarding.find_balance_sheet_figures',lambda *a: dict(
        current_total_assets=100.0,previous_total_assets=90.0,
        current_total_liabilities=40.0,previous_total_liabilities=35.0,
        unit='元',page_number=94,end_page_number=95))
    monkeypatch.setattr('src.audited_company_onboarding.find_cash_flow_figures',lambda *a: dict(
        current_operating_cash_flow=30.0,previous_operating_cash_flow=25.0,
        unit='元',page_number=99,end_page_number=100))
    return build_candidate_report_result(COMPANY,
        dict(report_year=2025,published_date='2026-04-30',title='宝钢股份2025年年度报告',url=SOURCE_URL),
        PDF,[dict(page_number=n,text=t) for n,t in (source if source is not None else pages())])


def test_real_two_page_income_is_read_without_reordering_and_reconciles_two_periods():
    source=pages(); original=deepcopy(source)
    figures,reconciliation=checked(source)
    assert source==original
    assert figures['page_number']==97 and figures['end_page_number']==98
    assert [figures['current_revenue'],figures['previous_revenue']]==[317507793966.66,322115845919.76]
    assert [figures['current_net_profit'],figures['previous_net_profit']]==[10345621735.27,7361925588.60]
    assert figures['unit']=='元'
    recovery=figures['attributable_layout_recovery']
    assert recovery['values']==SAMPLE['expected']
    assert recovery['pages']==dict(start=97,end=98)
    assert recovery['amount_pages']==dict(start=97,end=97)
    for segment in recovery['source_segments']:
        assert dict(source)[segment['page_number']][segment['start_offset']:segment['end_offset']]==segment['text']
    assert reconciliation['status']=='passed' and reconciliation['passed']
    row=reconciliation['evidence']['attributable_profit']
    assert row['values']==SAMPLE['expected']
    assert row['source_segments']==recovery['source_segments']
    assert all(c['passed'] for c in reconciliation['checks'])
    attribution=next(c for c in reconciliation['checks'] if c['key']=='profit_attribution')
    assert all(Decimal(attribution[p]['difference'])==0 for p in ('current','previous'))
    json.dumps(figures,allow_nan=False)
    json.dumps(reconciliation,allow_nan=False)


@pytest.mark.parametrize('page,old,new',[
    (97,'10,345,621,735.27','10,345,621,736.27'),
    (97,'7,361,925,588.60','7,361,925,589.60'),
    (98,'1,066,484,238.78','1,066,484,239.78'),
    (98,'1,205,724,086.59','1,205,724,087.59'),
    (97,'1,744,895,934.03','1,744,895,935.03'),
    (97,'771,603,046.41','771,603,047.41'),
])
def test_explicit_but_conflicting_values_are_read_then_rejected_by_arithmetic(page,old,new):
    figures,result=checked(replace(pages(),page,old,new))
    assert figures is not None
    assert not result['passed'] and result['status']=='mismatch'
    assert any(not c['passed'] for c in result['checks'])


@pytest.mark.parametrize('key',['current_net_profit','previous_net_profit'])
def test_reconciliation_rechecks_raw_pages_not_the_attached_recovery_values(key):
    source=pages(); figures=find_income_statement_figures(source)
    figures[key]+=1
    figures['attributable_layout_recovery']['values']=['1.00','2.00']
    result=check_general_income_reconciliation(source,figures,report_year=2025)
    assert result['status']=='mismatch'
    assert result['evidence']['attributable_profit']['values']==SAMPLE['expected']
    selected=next(c for c in result['checks'] if c['key']=='selected_attributable_profit')
    assert not selected['passed']


@pytest.mark.parametrize('page,old,new',[
    (97,'10,345,621,735.27',''),(97,'7,361,925,588.60',''),
    (97,'10,345,621,735.27','N/A'),(97,'7,361,925,588.60','7,361,925,588.60\n777.00'),
    (97,'（二）按所有权归属分类','母公司利润表\n（二）按所有权归属分类'),
    (97,'合并利润表','母公司利润表'),(97,'单位：元','单位：万元'),
    (97,'2024年度','2023年度'),
    (98,'损以“-”号填列）','损以“+”号填列）'),
    (98,'损以“-”号填列）','777.00\n损以“-”号填列）'),
    (98,'损以“-”号填列）','母公司利润表\n损以“-”号填列）'),
    (98,'98 / 245','99 / 245'),(98,'98 / 245','98 / 246'),
    (98,'宝山钢铁股份有限公司2025年年度报告','另一股份有限公司2025年年度报告'),
    (98,'1,066,484,238.78',''),(98,'1,205,724,086.59','1,205,724,086.59\n777.00'),
])
def test_damaged_crosspage_evidence_cannot_bypass_helper_via_normal_row_parser(page,old,new):
    _,result=checked(replace(pages(),page,old,new))
    assert not result['passed']
    assert result['status'] in ('missing_evidence','mismatch')


@pytest.mark.parametrize('kind',['nonadjacent','reversed','duplicate_page','duplicate_complete_row'])
def test_ambiguous_page_or_duplicate_profit_context_never_reconciles(kind):
    source=pages()
    if kind=='nonadjacent':source=[(n+1 if n==98 else n,t) for n,t in source]
    if kind=='reversed':source=source[::-1]
    if kind=='duplicate_page':source=source+[source[-1]]
    if kind=='duplicate_complete_row':
        source=replace(source,97,'（二）按所有权归属分类',
            '（二）按所有权归属分类\n1.归属于母公司股东的净利润（净亏损以“-”号填列）\n10,345,621,735.27\n7,361,925,588.60')
    _,result=checked(source)
    assert not result['passed']


def test_wrong_report_year_does_not_reuse_recovered_values():
    _,result=checked(pages(),year=2024)
    assert not result['passed'] and result['status']=='missing_evidence'


def test_candidate_snapshot_html_and_review_export_keep_actual_two_source_fragments(monkeypatch):
    result=candidate(monkeypatch)
    assert result['status']=='ready_for_human_review'
    assert result['income_reconciliation']['passed']
    assert len(result['income_layout_recoveries'])==1
    recovery=result['income_layout_recoveries'][0]
    raw_excerpt=recovery['excerpt']
    assert '7,361,925,588.60\n宝山钢铁股份有限公司2025年年度报告\n98 / 245\n损以“-”号填列）' in raw_excerpt
    assert result['metric_evidence']['net_profit']['excerpt']==raw_excerpt
    assert result['metric_evidence']['net_profit']['pages']==dict(start=97,end=98)
    snapshot=build_on_demand_financial_snapshot(COMPANY,result)
    assert snapshot['report']['income_layout_recoveries']==[recovery]
    profit=next(m for m in snapshot['metrics'] if m['key']=='net_profit')
    assert profit['current_yuan']==10345621735.27 and profit['previous_yuan']==7361925588.60
    assert profit['source']['pages']==dict(start=97,end=98)
    html=build_financial_snapshot_report_html(snapshot)
    assert '归母利润跨页读取依据' in html
    for segment in recovery['source_segments']:
        assert f"PDF第{segment['page_number']}页原始文字" in html
        assert '<pre>'+html_lib.escape(segment['text'])+'</pre>' in html
    review=build_financial_snapshot_review(snapshot)
    with pytest.raises(FinancialSnapshotReviewError):build_exportable_review_workpaper(review)
    for key in CORE_METRIC_KEYS:review=confirm_snapshot_metric(review,key)
    workpaper=build_exportable_review_workpaper(review)
    assert workpaper['report']['income_layout_recoveries']==[recovery]
    assert workpaper['source_fingerprint_sha256']==sha256(PDF).hexdigest()
    serialised=serialise_review_workpaper(workpaper)
    assert '%PDF' not in serialised
    assert len(serialised.encode())<64*1024
    assert json.loads(serialised)['report']['income_layout_recoveries'][0]['source_segments']==recovery['source_segments']


@pytest.mark.parametrize('damage',['amount','suffix'])
def test_failed_income_prevents_normalisation_and_review_confirmation(monkeypatch,damage):
    source=replace(pages(),97,'10,345,621,735.27','10,345,621,736.27') if damage=='amount' else replace(pages(),98,'损以“-”号填列）','损以“+”号填列）')
    result=candidate(monkeypatch,source)
    assert result['status']=='needs_review'
    assert not result['statement_checks']['income_statement_reconciled']
    snapshot=build_on_demand_financial_snapshot(COMPANY,result)
    assert all(m['current_yuan'] is None and m['previous_yuan'] is None for m in snapshot['metrics'])
    assert all(v is None for v in snapshot['ratios'].values())
    review=build_financial_snapshot_review(snapshot)
    with pytest.raises(FinancialSnapshotReviewError):confirm_snapshot_metric(review,'net_profit')
    with pytest.raises(FinancialSnapshotReviewError):build_exportable_review_workpaper(review)


def test_source_ui_shows_both_verbatim_segments_and_correct_official_page_links(monkeypatch):
    result=candidate(monkeypatch)
    snapshot=build_on_demand_financial_snapshot(COMPANY,result)
    recovery=snapshot['report']['income_layout_recoveries'][0]
    script="from src import app\napp._show_pdf_text_adjustments("+repr(snapshot)+")"
    at=AppTest.from_string(script).run()
    assert not at.exception
    assert [item.value for item in at.code]==[s['text'] for s in recovery['source_segments']]
    assert any('PDF第97页原始文字' in item.value for item in at.caption)
    assert any('PDF第98页原始文字' in item.value for item in at.caption)
    links=at.get('link_button')
    assert {item.proto.url for item in links}=={SOURCE_URL+'#page=97',SOURCE_URL+'#page=98'}
