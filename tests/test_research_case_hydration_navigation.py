"""A remounted storage component must not invent a read or a write receipt."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from src.china_stock import build_company_identity
from src.research_case import empty_research_case_store, reduce_research_case_store


NOTICE = '正在读取这台设备保存的研究案件，请稍候片刻。'


def saved_case():
    empty = empty_research_case_store()
    return reduce_research_case_store(empty, dict(
        command_id='hydrate-test-create', base_store_revision=0, action='create',
        emitted_at='2026-09-24T00:00:00+00:00', case_id='hydrate-test-case',
        company=build_company_identity('600519', '贵州茅台'), mode='current',
        as_of_date=None, effective_market_date='2026-09-24',
    ))


def session(monkeypatch, *, hydrated=False, status='pending', store=None):
    from src import app
    state = {
        app.RESEARCH_CASE_STORE_SESSION_KEY: deepcopy(store if store is not None else empty_research_case_store()),
        app.RESEARCH_CASE_HYDRATED_KEY: hydrated,
        app.RESEARCH_CASE_STORAGE_STATUS_KEY: status,
        '_wfz_research_case_writer_id': 'a' * 32,
    }
    messages = []
    monkeypatch.setattr(app, 'st', SimpleNamespace(
        session_state=state,
        info=lambda text: messages.append(('info', text)),
        warning=lambda text: messages.append(('warning', text)),
        error=lambda text: messages.append(('error', text)),
    ))
    return app, state, messages


@pytest.mark.parametrize('status', ['available', 'unavailable', 'invalid'])
@pytest.mark.parametrize('has_saved_case', [False, True])
def test_remount_with_no_new_browser_event_keeps_the_acknowledged_status(monkeypatch, status, has_saved_case):
    app, state, messages = session(monkeypatch, hydrated=True, status=status,
                                   store=saved_case() if has_saved_case else None)
    original = deepcopy(state)
    calls = []
    def remounted_component(**kwargs):
        calls.append(deepcopy(kwargs))
        return deepcopy(kwargs['default'])
    monkeypatch.setattr(app, '_RESEARCH_CASE_STORAGE', remounted_component)
    app._sync_research_case_store()
    app._render_research_case_storage_notice()
    assert state == original
    assert calls[0]['data']['known_storage_status'] == status
    assert calls[0]['default'] == {'snapshot': None, 'storage_status': status}
    assert not any(text == NOTICE for _, text in messages)
    if status == 'unavailable':
        assert any(kind == 'warning' and '无法使用本机存储' in text for kind, text in messages)
    elif status == 'invalid':
        assert any(kind == 'error' and '暂停写入' in text for kind, text in messages)
        assert not app._research_case_write_ready()


@pytest.mark.parametrize('browser_store', [None, saved_case()])
def test_first_visit_requires_an_actual_browser_response_before_hydration(monkeypatch, browser_store):
    app, state, messages = session(monkeypatch)
    monkeypatch.setattr(app, '_RESEARCH_CASE_STORAGE', lambda **kw: deepcopy(kw['default']))
    app._sync_research_case_store()
    app._render_research_case_storage_notice()
    assert state[app.RESEARCH_CASE_HYDRATED_KEY] is False
    assert not app._research_case_write_ready() and ('info', NOTICE) in messages
    # This models the subsequent component callback after localStorage read.
    monkeypatch.setattr(app, '_RESEARCH_CASE_STORAGE', lambda **kw: {
        'snapshot': deepcopy(browser_store), 'storage_status': 'available'})
    app._sync_research_case_store()
    messages.clear()
    app._render_research_case_storage_notice()
    assert state[app.RESEARCH_CASE_HYDRATED_KEY] is True
    assert state[app.RESEARCH_CASE_STORAGE_STATUS_KEY] == 'available'
    assert app._research_case_write_ready() and not messages
    assert state[app.RESEARCH_CASE_STORE_SESSION_KEY] == (browser_store or empty_research_case_store())


def test_pending_save_is_not_acknowledged_by_a_component_default(monkeypatch):
    app, state, _ = session(monkeypatch, hydrated=True, status='available')
    staged = saved_case()
    state[app.RESEARCH_CASE_PENDING_SESSION_KEY] = deepcopy(staged)
    state[app.RESEARCH_CASE_PENDING_BASE_KEY] = 0
    original = deepcopy(state)
    calls = []
    def no_browser_response(**kwargs):
        calls.append(deepcopy(kwargs))
        return deepcopy(kwargs['default'])
    monkeypatch.setattr(app, '_RESEARCH_CASE_STORAGE', no_browser_response)
    app._sync_research_case_store()
    assert state == original
    assert calls[0]['data']['write_enabled'] is True
    assert calls[0]['data']['known_snapshot'] == staged
    assert calls[0]['default']['snapshot'] is None
    assert not app._research_case_write_ready()
    monkeypatch.setattr(app, '_RESEARCH_CASE_STORAGE', lambda **kw: {
        'snapshot': deepcopy(staged), 'storage_status': 'available'})
    app._sync_research_case_store()
    assert state[app.RESEARCH_CASE_STORE_SESSION_KEY] == staged
    assert app.RESEARCH_CASE_PENDING_SESSION_KEY not in state
    assert app.RESEARCH_CASE_PENDING_BASE_KEY not in state
    assert app._research_case_write_ready()


@pytest.mark.parametrize('status', ['available', 'unavailable', 'invalid'])
def test_stale_pending_default_cannot_regress_a_completed_read_or_clear_a_write(monkeypatch, status):
    app, state, _ = session(monkeypatch, hydrated=True, status=status)
    pending = saved_case()
    state[app.RESEARCH_CASE_PENDING_SESSION_KEY] = deepcopy(pending)
    state[app.RESEARCH_CASE_PENDING_BASE_KEY] = 0
    original = deepcopy(state)
    # Older component state can still contain the old default after remount.
    monkeypatch.setattr(app, '_RESEARCH_CASE_STORAGE', lambda **kw: {
        'snapshot': deepcopy(pending), 'storage_status': 'pending'})
    app._sync_research_case_store()
    assert state == original
    assert not app._research_case_write_ready()


@pytest.mark.parametrize('status', ['unavailable', 'invalid'])
def test_actual_storage_failure_still_replaces_previous_available_status(monkeypatch, status):
    app, state, messages = session(monkeypatch, hydrated=True, status='available', store=saved_case())
    stored = deepcopy(state[app.RESEARCH_CASE_STORE_SESSION_KEY])
    monkeypatch.setattr(app, '_RESEARCH_CASE_STORAGE', lambda **kw: {'snapshot': None, 'storage_status': status})
    app._sync_research_case_store()
    app._render_research_case_storage_notice()
    assert state[app.RESEARCH_CASE_STORAGE_STATUS_KEY] == status
    assert state[app.RESEARCH_CASE_STORE_SESSION_KEY] == stored
    assert any(kind == ('warning' if status == 'unavailable' else 'error') for kind, _ in messages)
    if status == 'invalid':
        assert not app._research_case_write_ready()


def test_new_available_response_with_invalid_case_data_remains_fail_closed(monkeypatch):
    app, state, messages = session(monkeypatch, hydrated=True, status='available', store=saved_case())
    original = deepcopy(state[app.RESEARCH_CASE_STORE_SESSION_KEY])
    shallow_only = dict(schema_version='1.0', store_revision=2, active_case_id='bad', cases={'bad': {'case_id': 'bad'}})
    monkeypatch.setattr(app, '_RESEARCH_CASE_STORAGE', lambda **kw: {'snapshot': shallow_only, 'storage_status': 'available'})
    app._sync_research_case_store()
    app._render_research_case_storage_notice()
    assert state[app.RESEARCH_CASE_STORE_SESSION_KEY] == original
    assert state[app.RESEARCH_CASE_STORAGE_STATUS_KEY] == 'invalid'
    assert not app._research_case_write_ready()
    assert any(kind == 'error' for kind, _ in messages)


def test_real_navigation_preserves_hydrated_empty_store_when_new_page_has_no_component_event():
    # AppTest does not execute JS. It reproduces its observed protocol: an
    # initial read returns available; unchanged empty storage emits no event
    # when a page-specific component remounts, so that call returns default.
    script = '''
from copy import deepcopy
from unittest.mock import patch
import streamlit as st
from src import app

def storage(**kwargs):
    if st.session_state.get('test_surface') == 'workspace' and st.session_state.get('browser_has_replied'):
        return {'snapshot': None, 'storage_status': 'available'}
    return deepcopy(kwargs['default'])

def workspace():
    st.session_state['test_surface'] = 'workspace'
    app._sync_research_case_store()
    app._render_research_case_storage_notice()
    st.write('workspace-marker')
    if st.button('Open snapshot'):
        st.switch_page(snapshot_page)

def snapshot():
    st.session_state['test_surface'] = 'snapshot'
    app._sync_research_case_store()
    app._render_research_case_storage_notice()
    st.write('snapshot-marker')
    st.write('write-ready' if app._research_case_write_ready() else 'write-blocked')

workspace_page = st.Page(workspace, title='Workspace', default=True)
snapshot_page = st.Page(snapshot, title='Snapshot')
with patch.object(app, '_RESEARCH_CASE_STORAGE', storage):
    st.navigation([workspace_page, snapshot_page]).run()
'''
    at = AppTest.from_string(script).run()
    assert not at.exception and any(e.value == NOTICE for e in at.info)
    at.session_state['browser_has_replied'] = True
    at.run()
    assert not at.exception and not at.info
    at.button[0].click().run()
    assert not at.exception
    assert [e.value for e in at.markdown] == ['snapshot-marker', 'write-ready']
    assert not at.info and not at.warning and not at.error
    assert at.session_state['_wfz_research_case_storage_status'] == 'available'
    assert at.session_state['_wfz_research_case_hydrated'] is True
