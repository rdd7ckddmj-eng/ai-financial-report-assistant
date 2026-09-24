"""The input route must survive comparison export and historical replay."""
from copy import deepcopy
import json

import pytest
from streamlit.testing.v1 import AppTest

from src.public_financial_reconciliation import build_public_financial_reconciliation
from src.research_case import apply_case_patch, validate_research_case
from test_public_financial_reconciliation import inputs
from test_public_reconciliation_case import make_case, patch


@pytest.mark.parametrize('value,expected', [
    ('user_uploaded_official_report_candidate', 'user_uploaded_official_report_candidate'),
    ('redownloaded_exact_tested_official_report', 'redownloaded_exact_tested_official_report'),
    (None, 'not_recorded'), ('human_verified', 'not_recorded'),
    ({'route': 'redownloaded_exact_tested_official_report'}, 'not_recorded'),
    ([], 'not_recorded'),
])
def test_only_recorded_routes_round_trip_without_granting_review(value, expected):
    history, snapshot = inputs()
    snapshot['input_provenance'] = value
    before = deepcopy((history, snapshot))
    comparison = build_public_financial_reconciliation(history, snapshot)
    case = make_case(history)
    saved = json.loads(json.dumps(apply_case_patch(case, patch(case, history, snapshot))))
    validate_research_case(saved)
    payload = saved['artifacts'][0]['payload']
    assert comparison['annual_input_provenance'] == payload['annual_input_provenance'] == expected
    assert payload['annual_pdf_fingerprint'] == snapshot['source_fingerprint_sha256']
    assert payload['status'] == 'pending_human_review' and saved['evidence'] == []
    assert (history, snapshot) == before


@pytest.mark.parametrize('value,text', [
    ('redownloaded_exact_tested_official_report', '重新读取已测试的官方原件'),
    ('user_uploaded_official_report_candidate', '用户上传的年报候选'),
    (None, '此记录未保存输入方式'),
])
def test_live_and_saved_comparisons_display_recorded_route_without_fetch(monkeypatch, value, text):
    from src import app
    history, snapshot = inputs()
    snapshot['input_provenance'] = value
    def forbidden(*args, **kwargs):
        raise AssertionError('Rendering an available comparison must not fetch')
    monkeypatch.setattr(app, 'load_public_financial_history', forbidden)
    live = AppTest.from_string("import streamlit as st\nfrom src import app\napp._render_public_financial_reconciliation(st.session_state['snapshot'])")
    live.session_state['snapshot'] = snapshot
    live.session_state['_wfz_public_financial_histories'] = {history['company']['canonical_code']: history}
    live.session_state[app.FINANCIAL_SNAPSHOT_REVIEW_SESSION_KEY] = {'sentinel': 'unchanged'}
    live.run()
    assert not live.exception
    assert any(text in item.value for item in live.caption)
    assert live.session_state[app.FINANCIAL_SNAPSHOT_REVIEW_SESSION_KEY] == {'sentinel': 'unchanged'}
    case = make_case(history)
    case = apply_case_patch(case, patch(case, history, snapshot))
    saved = AppTest.from_string("import streamlit as st\nfrom src import app\napp._render_saved_financial_comparisons(st.session_state['case'])")
    saved.session_state['case'] = case
    saved.run()
    assert not saved.exception
    assert any(text in item.value for item in saved.caption)
