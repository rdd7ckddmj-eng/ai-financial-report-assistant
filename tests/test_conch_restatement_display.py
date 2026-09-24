"""Dual-source wording and saved replay must retain the two actual origins."""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.public_financial_history import build_public_financial_history
from src.research_case import apply_case_patch, validate_research_case
from test_public_reconciliation_case import make_case, patch


FIXTURE = json.loads((Path(__file__).parent / 'fixtures/conch_restatement_dual_source_2026H1.json').read_text())


def test_live_saved_and_exported_evidence_keep_original_and_restated_sources(monkeypatch):
    from src import app
    import src.public_financial_reconciliation as comparator
    snapshot = deepcopy(FIXTURE['annual_snapshot'])
    snapshot['input_provenance'] = 'redownloaded_exact_tested_official_report'
    history = build_public_financial_history(snapshot['company'], FIXTURE['source_rows'],
        fetched_at=FIXTURE['public_fetched_at'])
    monkeypatch.setattr(app, '_utc_today', lambda: datetime.fromisoformat(history['fetched_at']).date())
    def forbidden(*args, **kwargs):
        raise AssertionError('Saved explanations must not fetch or rematch')
    monkeypatch.setattr(app, 'load_public_financial_history', forbidden)
    live = AppTest.from_string("import streamlit as st\nfrom src import app\napp._render_public_financial_reconciliation(st.session_state['snapshot'])")
    live.session_state['snapshot'] = snapshot
    live.session_state['_wfz_public_financial_histories'] = {history['company']['canonical_code']: history}
    live.session_state[app.FINANCIAL_SNAPSHOT_REVIEW_SESSION_KEY] = {'sentinel': 'unchanged'}
    live.run()
    assert not live.exception
    assert live.session_state[app.FINANCIAL_SNAPSHOT_REVIEW_SESSION_KEY] == {'sentinel': 'unchanged'}
    case = make_case(history)
    saved_case = json.loads(json.dumps(apply_case_patch(case, patch(case, history, snapshot))))
    validate_research_case(saved_case)
    payload = saved_case['artifacts'][0]['payload']
    assert len(json.dumps(payload, ensure_ascii=False).encode()) < 20000
    assert payload['annual_input_provenance'] == 'redownloaded_exact_tested_official_report'
    assert saved_case['evidence'] == [] and payload['status'] == 'pending_human_review'
    assert [(r['key'], r['difference_yuan']) for r in payload['rows'] if r['status'] == 'amount_difference'] == [
        ('total_assets', -493995839.0), ('total_liabilities', -205443077.0)]
    monkeypatch.setattr(comparator, 'match_official_restatement_evidence', forbidden)
    saved = AppTest.from_string("import streamlit as st\nfrom src import app\napp._render_saved_financial_comparisons(st.session_state['case'])")
    saved.session_state['case'] = saved_case
    saved.run()
    for view in (live, saved):
        assert not view.exception
        text = '\n'.join(x.value for x in view.markdown)
        captions = '\n'.join(x.value for x in view.caption)
        assert text.count('已有对应的官方重述说明') == 2
        assert '年报原列值 256000730169' in text and '重述比较值 256494726008' in text
        assert '年报原列值 52284946547' in text and '重述比较值 52490389624' in text
        assert 'PDF 第 88 页' in text and 'PDF 第 61 页' in text
        assert '后续报告的元级报表未列调整前值' in captions
        assert '调整前 未记录' not in text
        assert '重新读取已测试的官方原件' in captions
    payload['rows'][3]['public_yuan'] += 1
    saved.session_state['case'] = saved_case
    saved.run()
    assert not saved.exception
    assert any('重述说明与此对照记录不一致' in x.value for x in saved.caption)
    assert sum('已有对应的官方重述说明' in x.value for x in saved.markdown) == 1
