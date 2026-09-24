"""Actual recovered PDF evidence survives snapshot/review/export, without confirmation."""
from copy import deepcopy
from pathlib import Path
import json
import pytest
from streamlit.testing.v1 import AppTest
from src.china_stock import build_company_identity
from src.on_demand_financial_snapshot import build_on_demand_financial_snapshot, build_financial_snapshot_report_html
from src.financial_snapshot_review import build_financial_snapshot_review, confirm_snapshot_metric, build_exportable_review_workpaper
from src.research_case_financial_review_bridge import _validate_workpaper, _build_artifact_payload
from test_pdf_actualtext_recovery import RECORDS


def candidate():
    result=json.loads((Path(__file__).parent/'fixtures/coverage15_unicom_candidate.json').read_text())
    result['pdf_native_text_recoveries']=deepcopy(RECORDS)
    return result

def snapshot():
    company=build_company_identity('600050');company['name']='中国联通'
    return build_on_demand_financial_snapshot(company,candidate())


def test_real_snapshot_keeps_two_readings_and_pending_review_within_existing_budget():
    raw=candidate();company=build_company_identity('600050');company['name']='中国联通'
    snap=build_on_demand_financial_snapshot(company,raw)
    assert snap['status']=='ready_for_human_review'
    assert snap['report']['pdf_native_text_recoveries']==RECORDS
    raw['pdf_native_text_recoveries'][0]['native_text']='modified'
    assert snap['report']['pdf_native_text_recoveries']==RECORDS
    review=build_financial_snapshot_review(snap)
    assert all(m['decision']=='pending' for m in review['metrics'])
    assert len(json.dumps(review,ensure_ascii=False,separators=(',',':')).encode())<=64*1024
    with pytest.raises(ValueError):build_exportable_review_workpaper(review)


def test_explicit_test_decisions_export_full_readings_then_bridge_bounded_reference():
    # Test decisions only; these fixtures do not claim a real human approval.
    review=build_financial_snapshot_review(snapshot())
    for metric in review['metrics']:review=confirm_snapshot_metric(review,metric['key'])
    paper=build_exportable_review_workpaper(review)
    assert paper['report']['pdf_native_text_recoveries']==RECORDS
    clean=_validate_workpaper({'company':paper['company'],'scope':{'mode':'current'}},paper)
    payload=_build_artifact_payload(clean)
    assert len(json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode())<=8000
    ref=payload['report']['reading_evidence_reference']
    assert [x['page_number'] for x in ref['native_pages']]==[77,78,79]
    assert ref['source_fingerprint_sha256']==paper['source_fingerprint_sha256']
    assert 'pdf_native_text_recoveries' not in payload['report']
    paper['report']['pdf_native_text_recoveries'][0]['native_text']+='corrupted'
    with pytest.raises(ValueError):_validate_workpaper({'company':paper['company'],'scope':{'mode':'current'}},paper)

@pytest.mark.parametrize('field,value',[('report_year',2024),('evidence_fingerprint_sha256','0'*64)])
def test_cross_document_or_year_evidence_cannot_normalize(field,value):
    raw=candidate();raw[field]=value
    company=build_company_identity('600050');company['name']='中国联通'
    with pytest.raises(ValueError):build_on_demand_financial_snapshot(company,raw)


def test_default_native_text_is_visible_and_escaped_with_physical_original_links():
    snap=snapshot();html=build_financial_snapshot_report_html(snap)
    assert 'PDF文字读取依据' in html and '第一节' in html and '392,222,880,560' in html
    at=AppTest.from_string('''
import streamlit as st
from src.app import _show_pdf_text_adjustments
_show_pdf_text_adjustments(st.session_state['snapshot'])
''');at.session_state['snapshot']=snap;at.run(timeout=20)
    assert not at.exception
    assert len(at.code)>=6
    assert any('第一节' in c.value for c in at.code)
    for page in [77,78,79]:assert any(f'第{page}页' in x.value for x in at.caption)
    snap['report']['pdf_native_text_recoveries'][0]['original_excerpt']='<script>bad()</script>'
    html=build_financial_snapshot_report_html(snap)
    assert '<script>bad()</script>' not in html and '&lt;script&gt;' in html


def test_annual_identity_source_pages_are_visible_and_case_reference_remains_bound():
    from test_annual_report_period_identity import recover, COMPANY, FINGERPRINT, FIXTURE
    from src.financial_report_reading_evidence import compact_reading_evidence
    report={'annual_identity_evidence':recover(),'source_url':FIXTURE['source_url'],'report_year':2025}
    at=AppTest.from_string('''
import streamlit as st
from src.app import _show_pdf_text_adjustments
_show_pdf_text_adjustments(st.session_state['reading'])
''');at.session_state['reading']={'report':report};at.run(timeout=20)
    assert not at.exception
    assert len(at.code)==len(report['annual_identity_evidence']['sources'])
    assert any('中国国际航空股份有限公司' in c.value for c in at.code)
    assert any('第70页' in c.value for c in at.caption)
    summary=compact_reading_evidence(report,fingerprint=FINGERPRINT,company=COMPANY)
    assert summary['reading_evidence_reference']['annual_identity_cross_checked'] is True
    with pytest.raises(ValueError):compact_reading_evidence(report,fingerprint='0'*64,company=COMPANY)
    with pytest.raises(ValueError):compact_reading_evidence(report,fingerprint=FINGERPRINT,company={**COMPANY,'code':'600050'})
