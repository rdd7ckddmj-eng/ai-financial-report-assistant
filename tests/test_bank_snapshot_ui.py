from streamlit.testing.v1 import AppTest


def test_company_selection_stabilizes_page_before_upload_form():
    at = AppTest.from_string('''
from src.app import render_financial_snapshot_page
render_financial_snapshot_page()
''').run()
    at.text_input(key='financial_snapshot_company_query').set_value('000001')
    next(b for b in at.button if b.label=='开始研究').click().run()
    assert not at.exception
    assert not any('请先输入' in x.value for x in at.warning)
    assert not any(b.label=='开始研究' for b in at.button)
    assert any(b.label=='用上传年报生成候选快照' for b in at.button)
    assert at.session_state['selected_company']['canonical_code']=='000001.SZ'


def test_bank_snapshot_displays_inapplicable_ratios_and_note_source():
    at = AppTest.from_string('''
import streamlit as st
from src import app
from src.china_stock import build_company_identity
from src.audited_company_onboarding import build_candidate_report_result
from src.on_demand_financial_snapshot import build_on_demand_financial_snapshot
from test_bank_group_note_extractor import fixture_pages
company=build_company_identity('000001','测试银行')
candidate=build_candidate_report_result(company,
    dict(report_year=2025,published_date='2026-03-21',title='测试银行2025年年度报告',
    url='https://static.cninfo.com.cn/test.pdf'),b'%PDF-test',
    [dict(page_number=n,text=t) for n,t in fixture_pages()])
st.session_state['selected_company']=company
st.session_state['on_demand_financial_snapshot']=build_on_demand_financial_snapshot(company,candidate)
app.render_financial_snapshot_page()
''').run()
    assert not at.exception
    ratios=[x for x in at.metric if x.label in ('净利率（同一提取口径）','经营现金流 / 净利润','资产负债率')]
    assert len(ratios)==3 and all(x.value=='不适用' for x in ratios)
    assert any('每股收益附注（归母利润）' in x.value for x in at.caption)
    assert any('已完成 0 / 5' in x.value for x in at.caption)
    assert next(b for b in at.button if b.label=='完成五项人工复核后才能导出底稿').disabled
