from datetime import date

from streamlit.testing.v1 import AppTest

from src.historical_game_mission import (
    HISTORICAL_MISSION_ID,
    build_historical_mission_reasoning_question,
    resolve_historical_mission_clock_boundary,
)


MISSION_PAGE_SCRIPT = """
from datetime import date

import pandas as pd
import streamlit as st

from src import app
from src.historical_game_mission import HISTORICAL_MISSION_ID

company = {
    "code": "600519",
    "name": "贵州茅台",
    "exchange": "SH",
    "exchange_name": "上海证券交易所",
    "canonical_code": "600519.SH",
}
dates = pd.date_range("2023-01-02", "2025-02-28", freq="B")
close = pd.Series([1000 + index * 0.5 for index in range(len(dates))])
market_frame = pd.DataFrame(
    {
        "date": dates,
        "open": close - 1,
        "high": close + 3,
        "low": close - 3,
        "close": close,
        "volume": 1_000_000,
        "amount": 1_000_000_000,
        "turnover": 1.5,
    }
)
market_frame.attrs["source"] = "测试公开行情"
announcements = pd.DataFrame(
    {
        "date": [date(2024, 9, 21)],
        "title": ["贵州茅台披露集中竞价回购股份方案"],
        "url": [
            "https://www.sse.com.cn/disclosure/listedinfo/announcement/"
            "c/new/2024-09-21/600519_20240921_CGR0.pdf"
        ],
        "category": ["资本管理"],
        "attention": ["高"],
    }
)

originals = {
    "apply_product_theme": app.apply_product_theme,
    "show_compact_page_header": app.show_compact_page_header,
    "_selected_company": app._selected_company,
    "_show_company_banner": app._show_company_banner,
    "load_a_share_history": app.load_a_share_history,
    "load_company_announcements": app.load_company_announcements,
    "_build_kline_figure": app._build_kline_figure,
    "plotly_chart": app.st.plotly_chart,
    "_show_verified_financial_history": app._show_verified_financial_history,
    "select_latest_annual_report": app.select_latest_annual_report,
    "show_product_footer": app.show_product_footer,
}
try:
    app.apply_product_theme = lambda: None
    app.show_compact_page_header = lambda *args: None
    app._selected_company = lambda: company
    app._show_company_banner = lambda selected: None
    app.load_a_share_history = lambda *args: market_frame
    app.load_company_announcements = lambda *args: announcements
    app._build_kline_figure = lambda *args: object()
    app.st.plotly_chart = lambda *args, **kwargs: None
    app._show_verified_financial_history = lambda *args: None
    app.select_latest_annual_report = lambda frame: None
    app.show_product_footer = lambda: None

    st.session_state.setdefault(
        "historical_game_mission_id",
        HISTORICAL_MISSION_ID,
    )
    st.session_state.setdefault("cash_case_stage", "case_completed")
    st.session_state.setdefault("cash_defense_lives", 3)
    app.render_historical_lens_page()
finally:
    app.apply_product_theme = originals["apply_product_theme"]
    app.show_compact_page_header = originals["show_compact_page_header"]
    app._selected_company = originals["_selected_company"]
    app._show_company_banner = originals["_show_company_banner"]
    app.load_a_share_history = originals["load_a_share_history"]
    app.load_company_announcements = originals["load_company_announcements"]
    app._build_kline_figure = originals["_build_kline_figure"]
    app.st.plotly_chart = originals["plotly_chart"]
    app._show_verified_financial_history = originals[
        "_show_verified_financial_history"
    ]
    app.select_latest_annual_report = originals[
        "select_latest_annual_report"
    ]
    app.show_product_footer = originals["show_product_footer"]
"""


MIGRATION_HANDOFF_SCRIPT = """
import streamlit as st

from src import app

st.session_state["game_player_name"] = "北辰"
st.session_state.setdefault("cash_case_stage", "migration")

original_switch_page = app._switch_page
try:
    def capture_route(target):
        st.session_state["captured_game_handoff_route"] = target

    app._switch_page = capture_route
    app.render_cash_migration_page()
finally:
    app._switch_page = original_switch_page
"""


WORKSPACE_MISSION_HINT_SCRIPT = """
import streamlit as st

from src import app
from src.historical_game_mission import HISTORICAL_MISSION_ID

st.session_state["historical_game_mission_id"] = HISTORICAL_MISSION_ID

originals = {
    "apply_product_theme": app.apply_product_theme,
    "show_compact_page_header": app.show_compact_page_header,
    "show_product_footer": app.show_product_footer,
}
try:
    app.apply_product_theme = lambda: None
    app.show_compact_page_header = lambda *args: None
    app.show_product_footer = lambda: None
    app.render_research_workspace_page()
finally:
    app.apply_product_theme = originals["apply_product_theme"]
    app.show_compact_page_header = originals["show_compact_page_header"]
    app.show_product_footer = originals["show_product_footer"]
"""


def test_migration_brief_requires_player_to_find_the_research_tool() -> None:
    """Accepting the brief should preserve context but open only the hub."""
    app_test = AppTest.from_string(MIGRATION_HANDOFF_SCRIPT).run()

    page_copy = "\n".join(
        [
            *(item.value for item in app_test.markdown),
            *(item.value for item in app_test.caption),
            *(item.value for item in app_test.info),
            *(item.label for item in app_test.button),
        ]
    )
    assert "Historical Lens" not in page_copy

    next(
        item
        for item in app_test.button
        if item.label == "接受委托｜前往研究中枢"
    ).click().run()

    assert not app_test.exception
    assert app_test.session_state["captured_game_handoff_route"] == "workspace"
    assert (
        app_test.session_state["historical_game_mission_id"]
        == HISTORICAL_MISSION_ID
    )
    assert app_test.session_state["selected_company"]["code"] == "600519"
    assert app_test.session_state["historical_prefill_date"] == "2024-09-18"
    assert app_test.session_state["cash_case_stage"] == "migration"


def test_workspace_only_hints_at_the_pending_game_tool() -> None:
    """The hub should describe the capability without naming the destination."""
    app_test = AppTest.from_string(WORKSPACE_MISSION_HINT_SCRIPT).run()

    assert not app_test.exception
    mission_hints = [
        item.value
        for item in app_test.info
        if "开放调查仍在进行" in item.value
    ]
    assert len(mission_hints) == 1
    assert "冻结过去信息截止线" in mission_hints[0]
    assert "Historical Lens" not in mission_hints[0]


def test_historical_mission_page_requires_date_and_reasoning() -> None:
    """The real page should reshuffle a wrong answer and complete both steps."""
    app_test = AppTest.from_string(MISSION_PAGE_SCRIPT).run()

    slider = next(
        item
        for item in app_test.slider
        if item.label == "拖动历史研究截止日"
    )
    slider.set_value(date(2024, 9, 21))
    next(
        item
        for item in app_test.button
        if item.label == "锁定这个时点并生成研究快照"
    ).click().run()
    next(
        item
        for item in app_test.button
        if item.label == "锁定当前日期为调查答案"
    ).click().run()

    assert not app_test.exception
    assert (
        app_test.session_state["historical_game_mission_date_completed"]
        == HISTORICAL_MISSION_ID
    )
    assert "historical_game_mission_completed" not in app_test.session_state

    boundary = resolve_historical_mission_clock_boundary(
        [date(2024, 9, 20), date(2024, 9, 23)],
        date(2024, 9, 21),
    )
    first_question = build_historical_mission_reasoning_question(boundary, 0)
    wrong_option = next(
        option
        for option in first_question["options"]
        if option != first_question["correct_option"]
    )
    next(
        item
        for item in app_test.radio
        if item.label == "选择唯一完整且严谨的调查结论"
    ).set_value(wrong_option)
    next(
        item
        for item in app_test.button
        if item.label == "提交最终调查结论"
    ).click().run()

    assert (
        app_test.session_state["historical_game_mission_reasoning_attempt"]
        == 1
    )
    assert app_test.session_state["cash_case_stage"] == "case_completed"
    assert app_test.session_state["cash_defense_lives"] == 3
    second_question = build_historical_mission_reasoning_question(boundary, 1)
    assert first_question["options"] != second_question["options"]

    next(
        item
        for item in app_test.radio
        if item.label == "选择唯一完整且严谨的调查结论"
    ).set_value(second_question["correct_option"])
    next(
        item
        for item in app_test.button
        if item.label == "提交最终调查结论"
    ).click().run()

    assert not app_test.exception
    assert (
        app_test.session_state["historical_game_mission_completed"]
        == HISTORICAL_MISSION_ID
    )
    assert app_test.session_state["cash_case_stage"] == "migration_completed"
    assert any(
        item.label == "调查完成｜进入首案封存"
        for item in app_test.button
    )
