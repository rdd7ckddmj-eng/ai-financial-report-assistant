from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest
from src.public_financial_history import build_public_financial_history
from src.china_stock import build_company_identity, DataSourceError
from test_public_financial_history import row


def fixture_history(code='000651'):
    return build_public_financial_history(build_company_identity(code,'测试公司'),[row(2024,code=code),row(code=code)],fetched_at=datetime.now(timezone.utc).isoformat())


@pytest.fixture(autouse=True)
def reset_forms():
    import streamlit as st
    st._main._form_data=None
    yield
    st._main._form_data=None


def test_unknown_company_panel_fetch_export_and_failed_refresh(monkeypatch):
    from src import app
    calls=[]
    def load(*args):
        calls.append(args)
        return fixture_history()
    load.clear=lambda *args: None
    monkeypatch.setattr(app,'load_public_financial_history',load)
    at=AppTest.from_string('''
from src import app
from src.china_stock import build_company_identity
app._render_public_financial_panel(build_company_identity('000651','格力电器'),key_prefix='test')
''').run()
    assert not at.exception and calls==[]
    at.button(key='test_fetch').click().run()
    assert not at.exception and len(calls)==1
    assert len(at.dataframe)==2
    assert len(at.get('download_button'))==2
    assert at.button(key='test_case').disabled
    def fail(*args): raise DataSourceError('模拟接口失败')
    fail.clear=lambda *args: None
    monkeypatch.setattr(app,'load_public_financial_history',fail)
    at.button(key='test_fetch').click().run()
    assert not at.exception and len(at.dataframe)==0
    assert any('模拟接口失败' in x.value for x in at.error)


def test_comparison_form_fetches_only_on_submit(monkeypatch):
    from src import app
    calls=[]
    def load(code,*args):
        calls.append(code)
        return fixture_history(code)
    monkeypatch.setattr(app,'load_public_financial_history',load)
    at=AppTest.from_string('from src import app\napp._render_public_company_comparison()').run()
    assert not at.exception and calls==[]
    at.text_input[0].set_value('000651，600036')
    at.button[0].click().run()
    assert not at.exception and calls==['000651','600036']
    assert len(at.dataframe)==1
    at.text_input[0].set_value('000651')
    at.button[0].click().run()
    assert not at.exception and len(at.dataframe)==0


def test_comprehensive_writeback_includes_public_source_atomically(monkeypatch):
    from src import app
    from src.comprehensive_research import build_comprehensive_research_brief
    from src.research_case import empty_research_case_store
    state={app.RESEARCH_CASE_STORAGE_STATUS_KEY:'ready'}
    monkeypatch.setattr(app,'st',SimpleNamespace(session_state=state))
    monkeypatch.setattr(app,'_research_case_store_snapshot',empty_research_case_store)
    staged=[]
    monkeypatch.setattr(app,'_stage_research_case_store',lambda store,**kwargs:staged.append(store))
    h=fixture_history()
    brief=build_comprehensive_research_brief(h['company'],public_financial_history=h,generated_on=datetime.now(timezone.utc).date())
    app._write_comprehensive_brief_to_research_case(h['company'],brief)
    assert len(staged)==1, state
    c=next(iter(staged[0]['cases'].values()))
    assert any(a['payload'].get('status')=='public_unverified' for a in c['artifacts'])
    assert c['evidence']==[]
