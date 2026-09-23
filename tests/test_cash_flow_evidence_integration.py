"""Original cash-flow layout evidence survives candidate, snapshot and export."""
from copy import deepcopy
import pytest

from streamlit.testing.v1 import AppTest
from src.on_demand_financial_snapshot import build_financial_snapshot_report_html
from test_industry_expansion_11 import candidate,sample


def test_actual_two_page_cash_label_evidence_survives_every_stage():
    source=sample('600406')
    raw,snapshot=candidate(source)
    evidence=raw['cash_flow_layout_recoveries']
    assert snapshot['status']=='ready_for_human_review'
    assert snapshot['report']['cash_flow_layout_recoveries']==evidence
    spans=evidence[0]['source_spans']
    assert [s['page_number'] for s in spans]==[134,135]
    for span in spans:
        page=next(p for p in source['pages'] if p['page_number']==span['page_number'])
        assert span['original_text'] in page['text']
    html=build_financial_snapshot_report_html(snapshot)
    assert '现金流换行与附注读取依据' in html
    assert 'PDF第134页' in html and 'PDF第135页' in html
    assert '-5,587,321,861.87' in html and '量净额' in html
    evidence[0]['source_spans'][0]['original_text']='changed'
    assert snapshot['report']['cash_flow_layout_recoveries'][0]['source_spans'][0]['original_text']!='changed'


def test_original_cash_text_is_escaped_in_html_and_visible_with_source_page_links():
    _,snapshot=candidate(sample('600406'))
    at=AppTest.from_string('''
import streamlit as st
from src.app import _show_pdf_text_adjustments
_show_pdf_text_adjustments(st.session_state['snapshot'])
''')
    at.session_state['snapshot']=deepcopy(snapshot)
    at.run(timeout=20)
    assert not at.exception
    assert len(at.code)==2
    assert any('-5,587,321,861.87' in c.value for c in at.code)
    evidence=snapshot['report']['cash_flow_layout_recoveries']
    evidence[0]['source_spans'][0]['original_text']='<script>bad()</script>'
    html=build_financial_snapshot_report_html(snapshot)
    assert '<script>bad()</script>' not in html
    assert '&lt;script&gt;bad()&lt;/script&gt;' in html


@pytest.mark.parametrize('broken',[None, {'source_spans':None}, {'source_spans':[None]}])
def test_damaged_persisted_cash_evidence_does_not_break_other_results(broken):
    _,snapshot=candidate(sample('600406'))
    snapshot['report']['cash_flow_layout_recoveries']=[broken]
    assert '核心财务快照' in build_financial_snapshot_report_html(snapshot)
    at=AppTest.from_string('''
import streamlit as st
from src.app import _show_pdf_text_adjustments
_show_pdf_text_adjustments(st.session_state['snapshot'])
''')
    at.session_state['snapshot']=snapshot
    at.run(timeout=20)
    assert not at.exception
