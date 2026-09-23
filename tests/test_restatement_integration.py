"""Known official-version differences stay unverified throughout the workflow."""
from copy import deepcopy
from datetime import datetime, timezone
import json

import pytest
from streamlit.testing.v1 import AppTest

from src.china_stock import build_company_identity
from src.public_financial_history import build_public_financial_history
from src.public_financial_reconciliation import build_public_financial_reconciliation
from src.research_case import apply_case_patch, validate_research_case
from src.research_case_workpaper import build_research_case_workpaper, ResearchCaseWorkpaperError
from test_public_financial_history import row
from test_public_financial_reconciliation import inputs
from test_public_reconciliation_case import make_case, patch


def restated_inputs(code='601088'):
    _, snapshot = inputs()
    company = build_company_identity(code, '中国神华' if code == '601088' else '汇川技术')
    snapshot['company'] = company
    if code == '601088':
        fingerprint = '7068df1231922b8a2fcfd0336d9ae6550dabf7c7edc152d680089df8cc126bd2'
        url = 'https://static.cninfo.com.cn/finalpage/2026-03-31/1225064293.PDF'
        values = {'total_assets': (627761000000, 903830000000, 148),
                  'total_liabilities': (146310000000, 300203000000, 150)}
        published, page_count = '2026-03-31', 310
    else:
        fingerprint = '622e4c655a31d41eca5e18fde18be214aeddef7d8a29a51d429efa1f322f8f01'
        url = 'https://static.cninfo.com.cn/finalpage/2026-04-28/1225208488.PDF'
        values = {'total_assets': (71314393635.15, 71314783635.15, 118)}
        published, page_count = '2026-04-28', 233
    snapshot['source_fingerprint_sha256'] = fingerprint
    snapshot['report'].update(source_url=url, published_date=published, page_count=page_count)
    public_values = dict(OPERATE_INCOME_PK=10000000, PARENTNETPROFIT=1000000,
        NETCASH_OPERATE_PK=1250000, TOTAL_ASSETS_PK=20000000, LIABILITY=8000000)
    fields = {'total_assets': 'TOTAL_ASSETS_PK', 'total_liabilities': 'LIABILITY'}
    for metric in snapshot['metrics']:
        if metric['key'] in values:
            annual, public, page = values[metric['key']]
            metric['current_yuan'] = annual
            metric['source'].update(raw_current_value=annual, original_unit='元',
                pages={'start': page, 'end': page}, excerpt='合并资产负债表对应原文行（集成测试）')
            public_values[fields[metric['key']]] = public
    public = build_public_financial_history(company, [row(code=code, **public_values)],
        fetched_at=datetime.now(timezone.utc).isoformat(timespec='seconds'))
    return public, snapshot


@pytest.mark.parametrize('code,expected', [('601088', 2), ('300124', 1)])
def test_exact_matches_explain_but_do_not_reclassify_or_mutate(code, expected):
    public, snapshot = restated_inputs(code)
    before = deepcopy((public, snapshot))
    result = build_public_financial_reconciliation(public, snapshot)
    explained = [r for r in result['rows'] if 'official_restatement_evidence' in r]
    assert len(explained) == expected
    assert all(r['status'] == 'amount_difference' for r in explained)
    assert all(r['official_restatement_evidence']['human_verification'] == 'not_performed' for r in explained)
    assert result['status'] == 'pending_human_review'
    assert (public, snapshot) == before


@pytest.mark.parametrize('change', ['sha', 'failed_check', 'pages', 'excerpt', 'amount', 'official_url', 'page_count', 'published_date'])
def test_nonmatching_or_incomplete_snapshot_never_gets_explanation(change):
    public, snapshot = restated_inputs('300124')
    metric = next(m for m in snapshot['metrics'] if m['key'] == 'total_assets')
    if change == 'sha': snapshot['source_fingerprint_sha256'] = '0' * 64
    if change == 'failed_check': snapshot['statement_checks']['income_statement_reconciled'] = False
    if change == 'pages': metric['source']['pages'] = None
    if change == 'excerpt': metric['source']['excerpt'] = ''
    if change == 'official_url': snapshot['report']['source_url'] = 'https://static.cninfo.com.cn/different.pdf'
    if change == 'page_count': snapshot['report']['page_count'] = 250
    if change == 'published_date': snapshot['report']['published_date'] = '2026-04-29'
    if change == 'amount':
        metric['current_yuan'] += 1
        metric['source']['raw_current_value'] += 1
    result = build_public_financial_reconciliation(public, snapshot)
    assert not any('official_restatement_evidence' in r for r in result['rows'])


def test_saved_explanations_survive_json_and_remain_analysis_under_size_limit():
    public, snapshot = restated_inputs()
    case = make_case(public)
    saved = apply_case_patch(case, patch(case, public, snapshot))
    serialized = json.dumps(saved, ensure_ascii=False, allow_nan=False)
    recovered = json.loads(serialized)
    validate_research_case(recovered)
    payload = recovered['artifacts'][0]['payload']
    assert len(json.dumps(payload, ensure_ascii=False).encode()) < 20000
    assert len([r for r in payload['rows'] if 'official_restatement_evidence' in r]) == 2
    assert payload['kind'] == 'analysis_output'
    assert recovered['evidence'] == []
    assert recovered['questions']['financial_quality']['status'] == 'in_progress'
    assert apply_case_patch(saved, patch(saved, public, snapshot)) == saved
    with pytest.raises(ResearchCaseWorkpaperError):
        build_research_case_workpaper(recovered, exported_at=datetime.now(timezone.utc).isoformat())


def test_live_and_saved_ui_show_original_evidence_without_changing_review(monkeypatch):
    from src import app
    import src.public_financial_reconciliation as comparator
    public, snapshot = restated_inputs('300124')
    case = make_case(public)
    case = apply_case_patch(case, patch(case, public, snapshot))
    def forbidden(*args, **kwargs):
        raise AssertionError('Saved evidence must not fetch or rematch')
    monkeypatch.setattr(app, 'load_public_financial_history', forbidden)
    at = AppTest.from_string("import streamlit as st\nfrom src import app\napp._render_public_financial_reconciliation(st.session_state['snapshot'])")
    at.session_state['snapshot'] = snapshot
    at.session_state['_wfz_public_financial_histories'] = {public['company']['canonical_code']: public}
    at.session_state[app.FINANCIAL_SNAPSHOT_REVIEW_SESSION_KEY] = {'sentinel': 'unchanged'}
    at.run()
    assert not at.exception
    assert any('已有对应的官方重述说明' in item.value for item in at.markdown)
    assert any('第 2、7 页' in item.value and '第 2、11 页' in item.value for item in at.caption)
    assert at.session_state[app.FINANCIAL_SNAPSHOT_REVIEW_SESSION_KEY] == {'sentinel': 'unchanged'}
    monkeypatch.setattr(comparator, 'match_official_restatement_evidence', forbidden)
    saved = AppTest.from_string("import streamlit as st\nfrom src import app\napp._render_saved_financial_comparisons(st.session_state['case'])")
    saved.session_state['case'] = case
    saved.run()
    assert not saved.exception
    assert any('已有对应的官方重述说明' in item.value for item in saved.markdown)
    for record in case['artifacts'][0]['payload']['rows']:
        record.pop('official_restatement_evidence', None)
    saved.session_state['case'] = case
    saved.run()
    assert not saved.exception
    assert not any('已有对应的官方重述说明' in item.value for item in saved.markdown)


def test_edited_imported_comparison_does_not_show_stale_matching_claim():
    public, snapshot = restated_inputs('300124')
    case = make_case(public)
    case = apply_case_patch(case, patch(case, public, snapshot))
    metric = next(r for r in case['artifacts'][0]['payload']['rows'] if r['key'] == 'total_assets')
    metric['public_yuan'] += 12345
    # Generic archive validation is intentionally not financial authentication.
    validate_research_case(case)
    at = AppTest.from_string("import streamlit as st\nfrom src import app\napp._render_saved_financial_comparisons(st.session_state['case'])")
    at.session_state['case'] = case
    at.run()
    assert not at.exception
    assert any('重述说明与此对照记录不一致' in item.value for item in at.caption)
    assert not any('已有对应的官方重述说明' in item.value for item in at.markdown)
    assert not any('本次公开值与调整后金额相同' in item.value for item in at.markdown)
