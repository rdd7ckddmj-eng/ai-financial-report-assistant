"""Exercise real Streamlit routing across an early component hydration rerun."""

import pytest
from streamlit.testing.v1 import AppTest


@pytest.mark.parametrize("target", [
    "render_home_page",
    "render_research_workspace_page",
    "render_financial_snapshot_page",
])
@pytest.mark.parametrize("hydrating_component", ["research", "game", "device"])
def test_first_hydration_rerun_retains_requested_page(target, hydrating_component):
    # AppTest cannot execute component JavaScript. Request the same full rerun
    # at each hydration boundary; real st.navigation/PagesManager still chooses
    # the next page. Browser tests separately exercise actual setStateValue.
    script = f'''
from contextlib import ExitStack
from functools import wraps
from unittest.mock import patch
import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx
from src import app

target = {target!r}
trigger = {hydrating_component!r}
if not st.session_state.get("_navigation_test_started"):
    st.session_state["_navigation_test_started"] = True
    requested_path = "" if target == "render_home_page" else target
    get_script_run_ctx().pages_manager.set_script_intent("", requested_path)

def hydrate(component):
    def sync():
        st.session_state["_navigation_restored_" + component] = True
        if component == trigger and not st.session_state.get("_navigation_hydrated"):
            st.session_state["_navigation_hydrated"] = True
            st.rerun()
    return sync

def render_marker(original):
    @wraps(original)
    def render():
        st.write(original.__name__)
        assert all(st.session_state.get("_navigation_restored_" + component)
                   for component in ("research", "game", "device"))
    return render

with ExitStack() as stack:
    for attribute, component in (
        ("_sync_browser_research_state", "research"),
        ("_sync_cash_game_progress", "game"),
        ("_sync_device_experience", "device"),
    ):
        stack.enter_context(patch.object(app, attribute, hydrate(component)))
    stack.enter_context(patch.object(app, "_render_research_sidebar_navigation", lambda *a: None))
    stack.enter_context(patch.object(app, "_render_device_experience_sidebar", lambda: None))
    for name in ("render_home_page", "render_research_workspace_page", "render_financial_snapshot_page"):
        stack.enter_context(patch.object(app, name, render_marker(getattr(app, name))))
    app.main()
'''
    result = AppTest.from_string(script).run(timeout=20)
    assert not result.exception
    assert result.session_state["_navigation_hydrated"] is True
    assert [item.value for item in result.markdown] == [target]
