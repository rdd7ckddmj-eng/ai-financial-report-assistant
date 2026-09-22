from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
import json
import pytest
from streamlit.testing.v1 import AppTest
from src.research_case import new_research_case, apply_case_patch, empty_research_case_store
from src.research_case_public_financial_bridge import build_public_reconciliation_case_patch
from src.research_case_workpaper import build_research_case_workpaper, ResearchCaseWorkpaperError
from test_public_financial_reconciliation import inputs


def make_case(history, mode='current'):
    now=datetime.now(timezone.utc).isoformat(timespec='seconds')
    return new_research_case('compare-case',history['company'],mode=mode,
        as_of_date=now[:10] if mode=='historical' else None,effective_market_date=now[:10],created_at=now)


def patch(case, history, snapshot):
    return build_public_reconciliation_case_patch(case,history,snapshot,emitted_at=datetime.now(timezone.utc).isoformat(timespec='seconds'))


def test_persistence_replay_export_and_no_verified_facts():
    history,snapshot=inputs(); case=make_case(history); original=deepcopy(case)
    update=patch(case,history,snapshot)
    saved=apply_case_patch(case,update)
    assert case==original
    assert saved['evidence']==[]
    assert saved['questions']['financial_quality']['status']=='in_progress'
    assert saved['case_brief']['contradictions']==[]
    assert apply_case_patch(saved,patch(saved,history,snapshot))==saved
    assert saved['artifacts'][0]['payload']['status']=='pending_human_review'
    assert len(json.dumps(update['artifact']['payload'],ensure_ascii=False).encode())<20000
    with pytest.raises(ResearchCaseWorkpaperError):
        build_research_case_workpaper(saved,exported_at=datetime.now(timezone.utc).isoformat())
    assert saved['artifacts'][0]['payload']['full_comparison_fingerprint']
    assert 'fingerprint' not in saved['artifacts'][0]['payload']


@pytest.mark.parametrize('status',['answered','needs_human_review'])
def test_preserves_existing_human_question_state(status):
    h,s=inputs(); c=make_case(h)
    c['questions']['financial_quality']['status']=status
    c['questions']['financial_quality']['summary']='已有人工结论'
    result=apply_case_patch(c,patch(c,h,s))
    assert result['questions']['financial_quality']['status']==status
    assert result['questions']['financial_quality']['summary']=='已有人工结论'


def test_historical_and_wrong_company_cannot_receive_comparison():
    h,s=inputs()
    with pytest.raises(ValueError): patch(make_case(h,'historical'),h,s)
    c=make_case(h); s['company']['code']='600036'
    with pytest.raises(ValueError): patch(c,h,s)


def test_transaction_and_unready_storage(monkeypatch):
    from src import app
    h,s=inputs(); state={app.RESEARCH_CASE_HYDRATED_KEY:True}
    monkeypatch.setattr(app,'st',SimpleNamespace(session_state=state))
    monkeypatch.setattr(app,'_research_case_store_snapshot',empty_research_case_store)
    staged=[]
    monkeypatch.setattr(app,'_stage_research_case_store',lambda result,**kw:staged.append(result))
    app._write_public_reconciliation_to_research_case(h['company'],h,s)
    assert len(staged)==1
    saved=next(iter(staged[0]['cases'].values()))
    assert len(saved['artifacts'])==1 and saved['evidence']==[]
    state[app.RESEARCH_CASE_PENDING_SESSION_KEY]={}
    with pytest.raises(ValueError): app._write_public_reconciliation_to_research_case(h['company'],h,s)
    assert len(staged)==1


def test_case_view_reads_saved_comparison_without_fetch(monkeypatch):
    from src import app
    h,s=inputs(); c=make_case(h); c=apply_case_patch(c,patch(c,h,s))
    def forbidden(*args): raise AssertionError('Unexpected network fetch')
    monkeypatch.setattr(app,'load_public_financial_history',forbidden)
    at=AppTest.from_string("import streamlit as st\nfrom src import app\napp._render_saved_financial_comparisons(st.session_state['saved_case'])")
    at.session_state['saved_case']=c
    at.run()
    assert not at.exception and len(at.dataframe)==1
    assert len(at.get('download_button'))==1


@pytest.mark.parametrize('pending,status,present,expected',[
    (True,'available',True,'等待浏览器'),
    (False,'available',True,'浏览器已确认'),
    (False,'unavailable',True,'暂存于当前会话'),
    (False,'available',False,'未能确认'),
])
def test_save_receipt_requires_browser_ack(monkeypatch,pending,status,present,expected):
    from src import app
    h,s=inputs(); c=make_case(h); update=patch(c,h,s)
    c=apply_case_patch(c,update)
    state={app.RESEARCH_CASE_STORAGE_STATUS_KEY:status,'_wfz_public_financial_save_notice':{
        'code':h['company']['canonical_code'],'artifact_id':update['artifact']['artifact_id']}}
    if pending: state[app.RESEARCH_CASE_PENDING_SESSION_KEY]={}
    messages=[]
    monkeypatch.setattr(app,'st',SimpleNamespace(session_state=state,info=messages.append,success=messages.append,warning=messages.append))
    monkeypatch.setattr(app,'_research_case_store_snapshot',lambda:{'cases':{'case':c} if present else {}})
    app._render_public_financial_save_notice(h['company'])
    assert any(expected in message for message in messages)
    assert '_wfz_public_financial_save_notice' in state


def test_saved_public_candidates_remain_readable_without_network(monkeypatch):
    from src import app
    from src.research_case_public_financial_bridge import build_public_financial_case_patch
    h,_=inputs(); c=make_case(h)
    c=apply_case_patch(c,build_public_financial_case_patch(c,h,emitted_at=datetime.now(timezone.utc).isoformat(timespec='seconds')))
    at=AppTest.from_string("import streamlit as st\nfrom src import app\napp._render_saved_public_financial_history(st.session_state['saved_case'])")
    at.session_state['saved_case']=c
    at.run()
    assert not at.exception and len(at.dataframe)==1
    assert len(at.get('download_button'))==1
