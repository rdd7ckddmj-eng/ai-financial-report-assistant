"""Live and stored TCL explanations identify both PDFs without approving amounts."""
from copy import deepcopy
from datetime import datetime
import json

from streamlit.testing.v1 import AppTest

from src.research_case import apply_case_patch, validate_research_case
from test_public_reconciliation_case import make_case, patch
from test_tcl_restatement_evidence import inputs


def test_live_saved_and_exported_tcl_explanations_keep_source_values_and_exact_wording(monkeypatch):
    from src import app
    import src.public_financial_reconciliation as comparator
    snapshot, history = inputs()
    snapshot['input_provenance'] = 'redownloaded_exact_tested_official_report'
    original = deepcopy(snapshot)
    monkeypatch.setattr(app, '_utc_today', lambda: datetime.fromisoformat(history['fetched_at']).date())
    def forbidden(*args, **kwargs): raise AssertionError('Saved evidence must not fetch or rematch.')
    monkeypatch.setattr(app, 'load_public_financial_history', forbidden)
    live = AppTest.from_string("import streamlit as st\nfrom src import app\napp._render_public_financial_reconciliation(st.session_state['snapshot'])")
    live.session_state['snapshot'] = snapshot
    live.session_state['_wfz_public_financial_histories'] = {history['company']['canonical_code']: history}
    live.session_state[app.FINANCIAL_SNAPSHOT_REVIEW_SESSION_KEY] = {'sentinel': 'unchanged'}
    live.run()
    assert not live.exception
    assert live.session_state['snapshot'] == original
    assert live.session_state[app.FINANCIAL_SNAPSHOT_REVIEW_SESSION_KEY] == {'sentinel': 'unchanged'}
    case = make_case(history)
    saved_case = json.loads(json.dumps(apply_case_patch(case, patch(case, history, snapshot))))
    validate_research_case(saved_case)
    payload = saved_case['artifacts'][0]['payload']
    assert len(json.dumps(payload, ensure_ascii=False).encode()) < 20000
    assert payload['status'] == 'pending_human_review' and saved_case['evidence'] == []
    assert [(r['key'], r['difference_yuan']) for r in payload['rows'] if r['status'] == 'amount_difference'] == [
        ('total_assets', -23487244.51), ('total_liabilities', 88959947.1)]
    monkeypatch.setattr(comparator, 'match_official_restatement_evidence', forbidden)
    saved = AppTest.from_string("import streamlit as st\nfrom src import app\napp._render_saved_financial_comparisons(st.session_state['case'])")
    saved.session_state['case'] = saved_case
    saved.run()
    for view in (live, saved):
        assert not view.exception
        text = '\n'.join(x.value for x in view.markdown)
        captions = '\n'.join(x.value for x in view.caption)
        assert text.count('已有对应的官方重述说明') == 2
        assert '年报原列值 117997173481.15' in text and '重述比较值 118020660725.66' in text
        assert '年报原列值 78738123809.74' in text and '重述比较值 78649163862.64' in text
        assert 'PDF 第 77 页' in text and 'PDF 第 51 页' in text
        assert '第8页主要财务指标摘要另并列' in text
        assert '没有列负债调整前值' in text
        assert '本条选用的后续金额页未并列调整前值；原值来自原年报。' in captions
        assert '后续报告的元级报表未列调整前值' not in captions
        assert '不证明供应商实际采集文档或入库时间' in captions
        assert '未完成人工复核' in captions
        assert '调整前 未记录' not in text
    payload['rows'][3]['public_yuan'] += 1
    saved.session_state['case'] = saved_case
    saved.run()
    assert not saved.exception
    assert any('重述说明与此对照记录不一致' in x.value for x in saved.caption)
    assert sum('已有对应的官方重述说明' in x.value for x in saved.markdown) == 1
