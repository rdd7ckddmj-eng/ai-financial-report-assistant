from copy import deepcopy
from datetime import datetime, timezone
import pytest
from streamlit.testing.v1 import AppTest
from src.china_stock import build_company_identity
from src.public_financial_history import build_public_financial_history
from src.public_financial_reconciliation import build_public_financial_reconciliation
from src.on_demand_financial_snapshot import build_on_demand_financial_snapshot
from test_on_demand_financial_snapshot import _candidate_result
from test_public_financial_history import row


def inputs():
    company=build_company_identity('000651','测试公司')
    snapshot=build_on_demand_financial_snapshot(company,_candidate_result())
    for metric in snapshot['metrics']:
        metric['source']['excerpt']='合并报表对应行，待人工核对'
    public=build_public_financial_history(company,[row(OPERATE_INCOME_PK=10000000,
        PARENTNETPROFIT=1000000,NETCASH_OPERATE_PK=1250000,TOTAL_ASSETS_PK=20000000,
        LIABILITY=8000000,TOTAL_EQUITY_PK=12000000)],fetched_at=datetime.now(timezone.utc).isoformat())
    return public,snapshot


def test_same_year_amounts_do_not_verify_or_modify_sources():
    public,snapshot=inputs(); before=deepcopy((public,snapshot))
    result=build_public_financial_reconciliation(public,snapshot)
    assert all(r['status']=='amount_close' for r in result['rows'])
    assert result['status']=='pending_human_review'
    assert result['rows'][0]['tolerance_yuan']==50
    assert result['rows'][0]['pages']=={'start':100,'end':101}
    assert '归母净利润' in ' '.join(result['rows'][1]['verification_tasks'])
    assert (public,snapshot)==before


def test_material_difference_with_large_amounts_not_hidden_by_relative_tolerance():
    public,snapshot=inputs()
    metric=snapshot['metrics'][0]
    metric['current_yuan']+=100
    metric['source']['raw_current_value']+=.01
    result=build_public_financial_reconciliation(public,snapshot)
    assert result['rows'][0]['status']=='amount_difference'
    assert result['rows'][0]['difference_yuan']==100


@pytest.mark.parametrize('change', ['wrong_company','wrong_year','bad_url','duplicate_metric','bad_fingerprint','nonfinite','bool','bad_pages'])
def test_rejects_cross_identity_invalid_provenance_and_amounts(change):
    public,snapshot=inputs()
    if change=='wrong_company': snapshot['company']=build_company_identity('600036')
    if change=='wrong_year': snapshot['report']['report_year']=2024
    if change=='bad_url': snapshot['report']['source_url']='https://example.com/report.pdf'
    if change=='duplicate_metric': snapshot['metrics'][1]=deepcopy(snapshot['metrics'][0])
    if change=='bad_fingerprint': snapshot['source_fingerprint_sha256']='not-a-hash'
    if change=='nonfinite': snapshot['metrics'][0]['current_yuan']=float('nan')
    if change=='bad_pages': snapshot['report']['page_count']='200'
    if change=='bool': snapshot['metrics'][0]['current_yuan']=True
    with pytest.raises(ValueError): build_public_financial_reconciliation(public,snapshot)


@pytest.mark.parametrize('change',['missing_raw','bad_unit','inconsistent_conversion','failed_check','missing_amount'])
def test_insufficient_data_is_not_compared(change):
    public,snapshot=inputs(); metric=snapshot['metrics'][0]
    if change=='missing_raw': metric['source']['raw_current_value']=None
    if change=='bad_unit': metric['source']['original_unit']='美元'
    if change=='inconsistent_conversion': metric['current_yuan']=1
    if change=='failed_check': snapshot['statement_checks']['income_statement_reconciled']=False
    if change=='missing_amount': metric['current_yuan']=None
    result=build_public_financial_reconciliation(public,snapshot)
    assert result['rows'][0]['status']=='not_comparable'
    assert result['rows'][0]['difference_yuan'] is None


def test_missing_excerpt_and_page_are_explicit_even_if_amount_close():
    public,snapshot=inputs(); snapshot['metrics'][0]['source']['pages']={'start':0,'end':1}
    snapshot['metrics'][0]['source']['excerpt']=''
    result=build_public_financial_reconciliation(public,snapshot)
    assert result['rows'][0]['pages'] is None
    assert '补充年报页码与对应原文摘录' in result['rows'][0]['verification_tasks']
    assert result['status']=='pending_human_review'


def test_ui_has_no_passive_fetch_and_does_not_change_review(monkeypatch):
    from src import app
    public,snapshot=inputs(); calls=[]
    def load(*args): calls.append(args); return public
    monkeypatch.setattr(app,'load_public_financial_history',load)
    # Fixture session values are populated before the script runs.
    at=AppTest.from_string('''
import streamlit as st
from src import app
app._render_public_financial_reconciliation(st.session_state['snapshot_fixture'])
''')
    at.session_state['snapshot_fixture']=snapshot
    at.session_state[app.FINANCIAL_SNAPSHOT_REVIEW_SESSION_KEY]={'sentinel':'unchanged'}
    at.run()
    assert not at.exception and calls==[]
    at.button(key='snapshot_public_compare_fetch').click().run()
    assert not at.exception and len(calls)==1
    assert len(at.dataframe)==1 and len(at.get('download_button'))==1
    assert at.session_state[app.FINANCIAL_SNAPSHOT_REVIEW_SESSION_KEY]=={'sentinel':'unchanged'}


def test_public_panel_link_opens_existing_snapshot_workflow(monkeypatch):
    from src import app
    public,_=inputs(); pages=[]
    monkeypatch.setattr(app,'_switch_page',lambda page: pages.append(page))
    at=AppTest.from_string("from src import app\nfrom src.china_stock import build_company_identity\napp._render_public_financial_panel(build_company_identity('000651','测试公司'),key_prefix='reconcile_link')")
    at.session_state['_wfz_public_financial_histories']={'000651.SZ':public}
    at.run()
    assert not at.exception
    at.button(key='reconcile_link_verify').click().run()
    assert not at.exception and pages==['financial_snapshot']
    assert at.session_state['selected_company']['canonical_code']=='000651.SZ'


def test_extreme_decimal_exponent_is_rejected_cleanly():
    public,snapshot=inputs()
    snapshot['metrics'][0]['current_yuan']='1e9999999999'
    with pytest.raises(ValueError): build_public_financial_reconciliation(public,snapshot)


def test_manual_input_provenance_survives_comparison():
    public,snapshot=inputs()
    snapshot['input_provenance']='user_uploaded_official_report_candidate'
    result=build_public_financial_reconciliation(public,snapshot)
    assert result['annual_input_provenance']=='user_uploaded_official_report_candidate'

@pytest.mark.parametrize('total,org,status',[(10000000,'证券','amount_close'),(None,'证券','not_comparable'),(10000000,'通用','not_comparable')])
def test_securities_total_revenue_uses_explicit_public_field(total,org,status):
    _,snapshot=inputs()
    snapshot['report']['statement_template']='securities_group_parent_yuan_v1'
    public=build_public_financial_history(snapshot['company'],[row(ORG_TYPE=org,OPERATE_INCOME_PK=777,TOTALOPERATEREVE=total)],fetched_at=datetime.now(timezone.utc).isoformat())
    result=build_public_financial_reconciliation(public,snapshot)['rows'][0]
    assert result['status']==status
    assert result['public_field']=='total_operating_revenue'
    assert result['label']=='营业总收入'
    assert result['public_yuan']==total


@pytest.mark.parametrize('template',['insurance_picc_million_v1','insurance_cpic_million_v1'])
@pytest.mark.parametrize('total,org,status',[(10000000,'保险','amount_close'),(None,'保险','not_comparable'),(10000000,'证券','not_comparable')])
def test_insurance_total_revenue_does_not_use_operating_income(template,total,org,status):
    _,snapshot=inputs()
    snapshot['report']['statement_template']=template
    public=build_public_financial_history(snapshot['company'],[row(ORG_TYPE=org,OPERATE_INCOME_PK=777,TOTALOPERATEREVE=total)],fetched_at=datetime.now(timezone.utc).isoformat())
    result=build_public_financial_reconciliation(public,snapshot)['rows'][0]
    assert result['status']==status
    assert result['public_field']=='total_operating_revenue'
    assert result['public_yuan']==total


def test_nci_operating_income_is_not_replaced_with_total_revenue():
    _,snapshot=inputs(); snapshot['report']['statement_template']='insurance_nci_four_column_v1'
    public=build_public_financial_history(snapshot['company'],[row(ORG_TYPE='保险',OPERATE_INCOME_PK=10000000,TOTALOPERATEREVE=777)],fetched_at=datetime.now(timezone.utc).isoformat())
    result=build_public_financial_reconciliation(public,snapshot)['rows'][0]
    assert result['status']=='amount_close'
    assert result['public_field']=='revenue'
