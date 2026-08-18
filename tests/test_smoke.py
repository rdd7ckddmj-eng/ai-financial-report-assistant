from datetime import date
from pathlib import Path

import pandas as pd


def _clear_streamlit_test_context() -> None:
    """Reset leaked form context between AppTest-generated scripts."""
    import streamlit as st

    st._main._form_data = None


def setup_function() -> None:
    _clear_streamlit_test_context()


def teardown_function() -> None:
    _clear_streamlit_test_context()


def _all_rendered_markup(app_test: object) -> str:
    """Collect Markdown and direct HTML nodes emitted by an AppTest run."""
    fragments = [item.value for item in app_test.markdown]
    for node in app_test._tree:
        if getattr(node, "type", None) != "html":
            continue
        body = getattr(getattr(node, "proto", None), "body", "")
        if isinstance(body, str):
            fragments.append(body)
    return "\n".join(fragments)


def test_app_uses_current_streamlit_width_api() -> None:
    """Keep removed container-width arguments out of production pages."""
    app_source = Path("src/app.py").read_text(encoding="utf-8")

    assert "use_container_width=" not in app_source


def test_project_smoke() -> None:
    assert 1 + 1 == 2


def test_research_run_summary_separates_speed_and_source_health() -> None:
    """Timing and source health must not be presented as investment quality."""
    from src.app import _build_research_run_summary

    summary = _build_research_run_summary(
        2.345,
        {"公开行情": True, "官方公告": False},
    )

    assert "本次处理用时 2.3 秒" in summary
    assert "公开行情：正常" in summary
    assert "官方公告：暂不可用" in summary
    assert "上涨" not in summary


def test_product_theme_preserves_sidebar_reopen_control() -> None:
    """Keep the collapsed navigation recoverable after visual customisation."""
    from streamlit.testing.v1 import AppTest

    script = """
from src.app import apply_product_theme

apply_product_theme()
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    theme_markup = "\n".join(item.value for item in app_test.markdown)
    assert '[data-testid="stExpandSidebarButton"]' in theme_markup
    assert '[data-testid="stSidebarCollapseButton"]' in theme_markup
    assert "visibility: visible !important" in theme_markup


def test_compact_page_header_escapes_dynamic_text() -> None:
    """Do not turn future data-driven labels into executable page markup."""
    from streamlit.testing.v1 import AppTest

    script = """
from src.app import show_compact_page_header

show_compact_page_header(
    "01 / TEST",
    "公司 <script>alert(1)</script>",
    "证据 & 审计",
)
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    header_markup = "\n".join(item.value for item in app_test.markdown)
    assert "<script>alert(1)</script>" not in header_markup
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in header_markup
    assert "证据 &amp; 审计" in header_markup


def test_platform_home_page_exposes_two_primary_modules() -> None:
    """Keep the platform purpose and its two entry points immediately clear."""
    from streamlit.testing.v1 import AppTest

    script = """
from src.app import render_home_page

render_home_page()
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    home_markup = "\n".join(item.value for item in app_test.markdown)
    assert "FINANCIAL RESEARCH LAB" in home_markup
    assert "别急着下结论" in home_markup
    assert "《消失的现金》" in home_markup
    assert "上市公司研究中枢" in home_markup
    button_labels = [button.label for button in app_test.button]
    assert button_labels == [
        "进入第一案",
        "进入研究中枢",
    ]


def test_navigation_exposes_chinese_home_and_one_canonical_game_entry() -> None:
    """Open on 中文首页 and keep every game scene behind one public URL."""
    from pathlib import Path

    source = Path("src/app.py").read_text(encoding="utf-8")

    home_start = source.index("home_page = st.Page(")
    game_start = source.index("game_page = st.Page(")
    home_definition = source[home_start:game_start]
    assert "default=True" in home_definition
    assert 'title="首页"' in home_definition
    assert 'visibility="hidden"' not in home_definition

    main_definition = source[source.index("def main() -> None:"):]
    for legacy_page in (
        "game_practice_page",
        "game_investigation_page",
        "game_evidence_page",
        "game_defense_page",
        "game_migration_page",
        "game_honour_page",
    ):
        assert f"{legacy_page} = st.Page(" not in main_definition

    navigation_start = source.index("navigation = st.navigation(")
    navigation_definition = source[navigation_start:source.index(
        "navigation.run()", navigation_start
    )]
    assert navigation_definition.index("home_page") < (
        navigation_definition.index("game_page")
    )
    assert navigation_definition.count("game_page") == 1


def test_game_intake_and_all_nine_scenes_share_one_screen_contract() -> None:
    """Keep the complete case inside one immersive, machine-checkable shell."""
    import re

    from streamlit.testing.v1 import AppTest

    scenes = (
        ("01", "briefing", False),
        ("02", "briefing", True),
        ("03", "practice", True),
        ("04", "investigation", True),
        ("05", "reading", True),
        ("06", "cross_check", True),
        ("07", "evidence", True),
        ("08", "defense", True),
        ("09", "migration", True),
        ("09", "migration_completed", True),
    )
    for expected_step, stage, has_player in scenes:
        script = f'''
import streamlit as st
from types import SimpleNamespace
from src import app
from src.cash_case_game import (
    build_cash_evidence_case,
    build_cash_evidence_lab_public_task,
)

if {has_player!r}:
    st.session_state["game_player_name"] = "北辰"
st.session_state["cash_case_stage"] = {stage!r}
st.session_state.setdefault("cash_defense_lives", 3)
st.session_state.setdefault("cash_defense_round_index", 0)
st.session_state.setdefault("cash_defense_attempt_index", 0)
st.session_state.setdefault("cash_defense_completed_explanations", [])
if {stage!r} in {{"reading", "cross_check", "evidence"}}:
    evidence_case = build_cash_evidence_case(0)
    lab_task = build_cash_evidence_lab_public_task(evidence_case)
    phase = {{
        "reading": "reading",
        "cross_check": "classification",
        "evidence": "chain",
    }}[{stage!r}]
    st.session_state["cash_evidence_attempt_index"] = 0
    st.session_state["cash_discovered_document_ids"] = [
        item["document_id"] for item in evidence_case["documents"]
    ]
    st.session_state["cash_evidence_lab_version"] = 1
    st.session_state["cash_evidence_lab_revision"] = 0
    st.session_state["cash_evidence_lab_task_id"] = lab_task["task_id"]
    st.session_state["cash_evidence_lab_phase"] = phase
    st.session_state["cash_evidence_lab_reading_viewed_ids"] = []
    st.session_state["cash_evidence_lab_reading_accepted_ids"] = []
    st.session_state["cash_evidence_lab_classification_accepted"] = {{}}
    st.session_state["cash_evidence_lab_chain_accepted"] = {{}}
    app.render_cash_evidence_lab = lambda **kwargs: SimpleNamespace(
        command=None
    )
if {stage!r} == "defense":
    app.render_cash_defense_committee = lambda **kwargs: SimpleNamespace(
        command=None
    )
original_storage = app._HONOUR_ARCHIVE_STORAGE
original_poster = app._HONOUR_POSTER
try:
    app._HONOUR_ARCHIVE_STORAGE = lambda **kwargs: SimpleNamespace(
        record=kwargs["default"]["record"], storage_status="available"
    )
    app._HONOUR_POSTER = lambda **kwargs: None
    app.render_game_hub_page()
finally:
    app._HONOUR_ARCHIVE_STORAGE = original_storage
    app._HONOUR_POSTER = original_poster
'''
        app_test = AppTest.from_string(script).run(timeout=10)

        assert not app_test.exception
        page_markup = _all_rendered_markup(app_test)
        assert re.search(
            r'data-wfz-game-screen=["\']true["\']',
            page_markup,
        )
        assert re.search(
            rf'data-game-step=["\']{expected_step}["\']',
            page_markup,
        )


def test_game_route_uses_fixed_viewport_with_internal_scene_scroll() -> None:
    """The game behaves like one screen, not a long scrolling web page."""
    from streamlit.testing.v1 import AppTest

    script = """
from src.app import apply_cash_game_theme

apply_cash_game_theme()
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    theme_markup = "\n".join(item.value for item in app_test.markdown)
    assert "height: 100dvh !important" in theme_markup
    assert '[data-testid="stMain"]' in theme_markup
    assert "overflow: hidden !important" in theme_markup
    assert ".st-key-cash_game_scene_content" in theme_markup
    assert "overflow-y: auto" in theme_markup
    assert "position: fixed !important" in theme_markup
    assert "bottom: clamp(1rem, 2.5vh, 1.8rem)" in theme_markup
    assert ".wfz-game-exit" in theme_markup
    assert 'html body section[data-testid="stSidebar"]' in theme_markup
    assert "visibility: hidden !important" in theme_markup


def test_game_controls_can_return_one_scene_and_rename_without_reset() -> None:
    """Back and rename must be reversible controls, not destructive links."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from src.app import render_game_hub_page

st.session_state.setdefault("game_player_name", "北辰")
st.session_state.setdefault("cash_case_stage", "practice")
st.session_state.setdefault("cash_defense_lives", 3)
render_game_hub_page()
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    for expected_label in ("← 上一步", "修改代号", "重新开始"):
        assert any(item.label == expected_label for item in app_test.button)

    next(
        item for item in app_test.button if item.label == "修改代号"
    ).click().run()
    rename_input = next(
        item for item in app_test.text_input
        if item.label == "新的调查员代号"
    )
    rename_input.set_value("苍穹").run()
    next(
        item for item in app_test.button
        if item.label == "确认修改｜保留当前进度"
    ).click().run()

    assert app_test.session_state["game_player_name"] == "苍穹"
    assert app_test.session_state["cash_case_stage"] == "practice"

    next(
        item for item in app_test.button if item.label == "← 上一步"
    ).click().run()
    assert app_test.session_state["cash_case_stage"] == "briefing"


def test_game_restart_offers_keep_or_replace_identity_paths() -> None:
    """Restart requires a choice and can return to either requested scene."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from src.app import render_game_hub_page

if "game_player_name" not in st.session_state:
    st.session_state["game_player_name"] = "北辰"
    st.session_state["cash_case_stage"] = "defense"
    st.session_state["cash_defense_lives"] = 1
    st.session_state["cash_defense_round_index"] = 1
    st.session_state["cash_defense_attempt_index"] = 5
render_game_hub_page()
"""
    keep_test = AppTest.from_string(script).run()
    next(
        item for item in keep_test.button if item.label == "重新开始"
    ).click().run()
    assert any(
        item.label == "保留代号｜从教学重新开始"
        for item in keep_test.button
    )
    assert any(
        item.label == "清除代号｜返回取名页"
        for item in keep_test.button
    )
    next(
        item for item in keep_test.button
        if item.label == "保留代号｜从教学重新开始"
    ).click().run()

    assert keep_test.session_state["game_player_name"] == "北辰"
    assert keep_test.session_state["cash_case_stage"] == "briefing"
    assert keep_test.session_state["cash_defense_lives"] == 3
    assert "cash_defense_attempt_index" not in keep_test.session_state

    identity_test = AppTest.from_string(script).run()
    next(
        item for item in identity_test.button if item.label == "重新开始"
    ).click().run()
    next(
        item for item in identity_test.button
        if item.label == "清除代号｜返回取名页"
    ).click().run()

    assert identity_test.session_state["cash_identity_required"] is True
    assert identity_test.session_state["cash_case_stage"] == "briefing"
    identity_input = next(
        item for item in identity_test.text_input
        if item.label == "在案件终端输入调查员代号"
    )
    identity_input.set_value("新调查员").run()
    next(
        item for item in identity_test.button
        if item.label == "确认代号｜进入零基础教学"
    ).click().run()

    assert identity_test.session_state["game_player_name"] == "新调查员"
    assert "cash_identity_required" not in identity_test.session_state


def test_game_hud_uses_direct_html_instead_of_markdown_code_fences() -> None:
    """Optional HUD fragments must never expose raw tags to the player."""
    from streamlit.testing.v1 import AppTest

    script = """
from src.app import _show_cash_game_stage

_show_cash_game_stage(
    1,
    "剧情进入｜建立调查身份",
    "在案件终端取名。",
    "别猜。",
    prologue=True,
)
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    rendered_markup = _all_rendered_markup(app_test)
    assert 'data-game-step="01"' in rendered_markup
    assert not any(
        "<div class=" in item.value
        for item in app_test.code
    )


def test_research_terminal_renders_without_live_requests() -> None:
    """Keep the existing real-company research entry intact after the split."""
    from streamlit.testing.v1 import AppTest

    script = """
from src.app import render_research_terminal_page

render_research_terminal_page()
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    home_markup = "\n".join(item.value for item in app_test.markdown)
    home_subheaders = "\n".join(
        item.value for item in app_test.subheader
    )
    assert "RESEARCH PIPELINE" in home_markup
    assert "FANGZHENG AI" in home_markup
    assert "更快完成有证据的第一轮公司研究" in home_subheaders
    assert "把核心资料接到同一入口" in home_markup
    assert "把数据变成可继续核验的问题" in home_markup
    assert "输出一份可复核的研究底稿" in home_markup
    assert "优势不在于拥有比 Wind 等商业数据库更多的数据" in home_markup
    assert "A 股按需研究层" in home_markup
    assert "6 家公司 · 21 个财务期间 · 23 个发布版本" in home_markup
    assert (
        "贵州茅台 · 五粮液 · 泸州老窖 · 宁德时代 · 比亚迪 · 美的集团"
        in home_markup
    )
    assert "不是实时交易终端或商业金融数据库的替代品" in home_markup
    assert any(
        button.label == "进入研究工具导航｜按任务查看全部功能"
        for button in app_test.button
    )
    assert len(app_test.button) == 5


def test_game_hub_opens_the_first_teaching_node_and_locks_later_mission() -> None:
    """Open role creation directly instead of showing a separate game hub."""
    from streamlit.testing.v1 import AppTest

    script = """
from src.app import render_game_hub_page

render_game_hub_page()
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    page_markup = _all_rendered_markup(app_test)
    assert "《消失的现金》" in page_markup
    assert "九幕连续调查" in page_markup
    assert any(
        item.label == "确认代号｜进入零基础教学"
        for item in app_test.button
    )
    assert "中文或英文，最多12个字符" == app_test.text_input[0].placeholder
    assert "代号不是账户" in page_markup
    assert "wfz-intake-scene" in page_markup


def test_completed_game_unlocks_bounded_honour_archive() -> None:
    """Only a fully migrated case should show the archive and poster."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from types import SimpleNamespace
from src import app
from src.historical_game_mission import HISTORICAL_MISSION_ID

st.session_state["game_player_name"] = "北辰"
st.session_state["cash_case_stage"] = "migration_completed"
st.session_state["historical_game_mission_completed"] = HISTORICAL_MISSION_ID
st.session_state["cash_game_keepsakes"] = ["unwritten_verdict_seal"]
original_storage = app._HONOUR_ARCHIVE_STORAGE
original_poster = app._HONOUR_POSTER
try:
    app._HONOUR_ARCHIVE_STORAGE = lambda **kwargs: SimpleNamespace(
        record=kwargs["default"]["record"], storage_status="available"
    )
    app._HONOUR_POSTER = lambda **kwargs: None
    app.render_game_hub_page()
finally:
    app._HONOUR_ARCHIVE_STORAGE = original_storage
    app._HONOUR_POSTER = original_poster
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    page_markup = _all_rendered_markup(app_test)
    assert "首案封存｜拒绝用明天解释今天" in page_markup
    assert "wfz-honour-archive" in page_markup
    assert "北辰" in page_markup
    assert "测试赛季 · 本设备通关位次" in page_markup
    assert "000001" in page_markup
    assert "不是全站排行榜" in "\n".join(
        item.value for item in app_test.caption
    )
    assert "你也想发抖音吗" in page_markup


def test_cash_case_scene_mounts_a_playable_component_without_form_widgets() -> None:
    """Scene three is one interactive game surface, not a disguised form."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from types import SimpleNamespace
from src import app

def fake_component(**kwargs):
    st.session_state["_test_dual_clock_state"] = kwargs["state"]
    return SimpleNamespace(command=None)

st.session_state["game_player_name"] = "北辰"
st.session_state.setdefault("cash_case_stage", "practice")
st.session_state.setdefault("cash_case_attempt_index", 0)
app.render_cash_dual_clock_game = fake_component
app.render_game_hub_page()
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    assert not app_test.radio
    assert not app_test.multiselect
    assert app_test.session_state["cash_dual_clock_phase"] == "routes"
    assert app_test.session_state["cash_dual_clock_version"] == 1
    state = app_test.session_state["_test_dual_clock_state"]
    assert len(state["cards"]) == 6
    assert {item["id"] for item in state["zones"]} == {
        "profit", "cash", "both", "neither"
    }
    assert state["keepsake_discovered"] is False


def test_wrong_clock_assignment_stays_on_the_same_dossier() -> None:
    """Only conflicting cards bounce; accepted work remains on the desk."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from types import SimpleNamespace
from src import app
from src.cash_case_game import build_cash_timing_question

question = build_cash_timing_question(0)
if "_test_dual_clock_seeded" not in st.session_state:
    st.session_state["_test_dual_clock_seeded"] = True
    st.session_state["_test_dual_clock_command"] = {
        "schema_version": 1,
        "command_id": "wrong-route-1",
        "question_id": question["question_id"],
        "revision": 0,
        "action": "submit_routes",
        "bins": {
            "contract_signed": "neither",
            "service_completed": "profit",
            "expense_incurred": "profit",
            "expense_paid": "cash",
            "cash_collected": "cash",
            "future_payment_plan": "cash",
        },
    }

def fake_component(**kwargs):
    return SimpleNamespace(
        command=st.session_state.pop("_test_dual_clock_command", None)
    )

st.session_state["game_player_name"] = "北辰"
st.session_state["cash_case_stage"] = "practice"
st.session_state.setdefault("cash_case_attempt_index", 0)
app.render_cash_dual_clock_game = fake_component
app.render_game_hub_page()
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    assert app_test.session_state["cash_case_attempt_index"] == 0
    assert "cash_clock_assignment_unlocked" not in app_test.session_state
    assert app_test.session_state["cash_dual_clock_phase"] == "routes"
    assert app_test.session_state["cash_dual_clock_revision"] == 0
    placements = app_test.session_state[
        "_wfz_cash_dual_clock_placements_routes"
    ]
    assert len(placements) == 5
    assert "future_payment_plan" not in placements
    feedback = app_test.session_state["_wfz_cash_dual_clock_feedback"]
    assert feedback["title"] == "只退回有矛盾的材料"


def test_correct_clock_routes_unlock_the_gap_token_scene() -> None:
    """Correct dragging advances one scene and never exposes a radio quiz."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from types import SimpleNamespace
from src import app
from src.cash_case_game import build_cash_timing_question

question = build_cash_timing_question(0)
if "_test_dual_clock_seeded" not in st.session_state:
    st.session_state["_test_dual_clock_seeded"] = True
    st.session_state["_test_dual_clock_command"] = {
        "schema_version": 1,
        "command_id": "correct-route-1",
        "question_id": question["question_id"],
        "revision": 0,
        "action": "submit_routes",
        "bins": {
            "contract_signed": "neither",
            "service_completed": "profit",
            "expense_incurred": "profit",
            "expense_paid": "cash",
            "cash_collected": "cash",
            "future_payment_plan": "neither",
        },
    }

def fake_component(**kwargs):
    st.session_state["_test_dual_clock_state"] = kwargs["state"]
    return SimpleNamespace(
        command=st.session_state.pop("_test_dual_clock_command", None)
    )

st.session_state["game_player_name"] = "北辰"
st.session_state["cash_case_stage"] = "practice"
st.session_state.setdefault("cash_case_attempt_index", 0)
app.render_cash_dual_clock_game = fake_component
app.render_game_hub_page()
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    assert app_test.session_state["cash_clock_assignment_unlocked"] is True
    assert app_test.session_state["cash_dual_clock_phase"] == "hypothesis"
    assert app_test.session_state["cash_dual_clock_revision"] == 1
    assert not app_test.radio
    state = app_test.session_state["_test_dual_clock_state"]
    assert state["phase"] == "hypothesis"
    assert state["gap_token"]["title"] == "100 万元"


def test_wrong_gap_hypothesis_preserves_completed_clock_routes() -> None:
    """A wrong hypothesis should not make the player sort six facts again."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from types import SimpleNamespace
from src import app
from src.cash_case_game import build_cash_timing_question

question = build_cash_timing_question(0)
accepted_routes = {
    "contract_signed": "neither",
    "service_completed": "profit",
    "expense_incurred": "profit",
    "expense_paid": "cash",
    "cash_collected": "cash",
    "future_payment_plan": "neither",
}
if "_test_dual_clock_seeded" not in st.session_state:
    st.session_state["_test_dual_clock_seeded"] = True
    st.session_state["cash_dual_clock_version"] = 1
    st.session_state["cash_dual_clock_revision"] = 1
    st.session_state["cash_dual_clock_phase"] = "hypothesis"
    st.session_state["cash_clock_assignment_unlocked"] = True
    st.session_state["_wfz_cash_dual_clock_placements_routes"] = accepted_routes
    st.session_state["_test_dual_clock_command"] = {
        "schema_version": 1,
        "command_id": "wrong-hypothesis-1",
        "question_id": question["question_id"],
        "revision": 1,
        "action": "submit_hypothesis",
        "hypothesis_id": "proven_fraud",
    }

def fake_component(**kwargs):
    st.session_state["_test_dual_clock_state"] = kwargs["state"]
    return SimpleNamespace(
        command=st.session_state.pop("_test_dual_clock_command", None)
    )

st.session_state["game_player_name"] = "北辰"
st.session_state["cash_case_stage"] = "practice"
st.session_state.setdefault("cash_case_attempt_index", 0)
app.render_cash_dual_clock_game = fake_component
app.render_game_hub_page()
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    assert app_test.session_state["cash_dual_clock_phase"] == "hypothesis"
    assert app_test.session_state["cash_dual_clock_revision"] == 1
    assert app_test.session_state["cash_clock_assignment_unlocked"] is True
    assert app_test.session_state[
        "_wfz_cash_dual_clock_placements_routes"
    ] == {
        "contract_signed": "neither",
        "service_completed": "profit",
        "expense_incurred": "profit",
        "expense_paid": "cash",
        "cash_collected": "cash",
        "future_payment_plan": "neither",
    }
    assert app_test.session_state[
        "_wfz_cash_dual_clock_placements_hypothesis"
    ] == {}
    feedback = app_test.session_state["_wfz_cash_dual_clock_feedback"]
    assert feedback["title"] == "只退回有矛盾的材料"
    assert "不能直接证明造假" in feedback["message"]
    assert not app_test.radio
    assert not app_test.multiselect


def test_correct_orders_unlock_door_then_open_evidence_room() -> None:
    """The issued order must pass Python checks before the office opens."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from types import SimpleNamespace
from src import app
from src.cash_case_game import build_cash_timing_question

question = build_cash_timing_question(0)
if "_test_dual_clock_seeded" not in st.session_state:
    st.session_state["_test_dual_clock_seeded"] = True
    st.session_state["cash_dual_clock_version"] = 1
    st.session_state["cash_dual_clock_revision"] = 2
    st.session_state["cash_dual_clock_phase"] = "orders"
    st.session_state["cash_clock_assignment_unlocked"] = True
    st.session_state["cash_gap_hypothesis_unlocked"] = True
    st.session_state["_test_dual_clock_command"] = {
        "schema_version": 1,
        "command_id": "correct-orders-1",
        "question_id": question["question_id"],
        "revision": 2,
        "action": "submit_orders",
        "pockets": {
            "income_boundary": "contract_acceptance",
            "receivable_existence": "receivable_aging",
            "subsequent_cash": "bank_statement",
        },
        "discarded": ["management_promise"],
    }

def fake_component(**kwargs):
    st.session_state["_test_dual_clock_state"] = kwargs["state"]
    return SimpleNamespace(
        command=st.session_state.pop("_test_dual_clock_command", None)
    )

st.session_state["game_player_name"] = "北辰"
st.session_state.setdefault("cash_case_stage", "practice")
st.session_state.setdefault("cash_case_attempt_index", 0)
app.render_cash_dual_clock_game = fake_component
app.render_game_hub_page()
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    assert app_test.session_state["cash_dual_clock_phase"] == "door"
    assert app_test.session_state["cash_dual_clock_revision"] == 3
    assert app_test.session_state[
        "cash_investigation_orders_unlocked"
    ] is True
    assert app_test.session_state[
        "_wfz_cash_dual_clock_placements_orders"
    ] == {
        "contract_acceptance": "income_boundary",
        "receivable_aging": "receivable_existence",
        "bank_statement": "subsequent_cash",
        "management_promise": "discarded",
    }
    door_state = app_test.session_state["_test_dual_clock_state"]
    assert door_state["phase"] == "door"

    question_id = door_state["question_id"] if "question_id" in door_state else None
    if question_id is None:
        from src.cash_case_game import build_cash_timing_question

        question_id = build_cash_timing_question(0)["question_id"]
    app_test.session_state["_test_dual_clock_command"] = {
        "schema_version": 1,
        "command_id": "open-door-1",
        "question_id": question_id,
        "revision": 3,
        "action": "open_door",
    }
    app_test.run()

    assert not app_test.exception
    assert app_test.session_state["cash_case_stage"] == "investigation"
    assert app_test.session_state["cash_evidence_attempt_index"] == 0
    assert app_test.session_state["cash_discovered_document_ids"] == []


def test_discover_dual_clock_keepsake_does_not_advance_the_phase() -> None:
    """A hidden-object discovery is optional and must not skip learning."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from types import SimpleNamespace
from src import app
from src.cash_case_game import build_cash_timing_question

question = build_cash_timing_question(0)
if "_test_dual_clock_seeded" not in st.session_state:
    st.session_state["_test_dual_clock_seeded"] = True
    st.session_state["_test_dual_clock_command"] = {
        "schema_version": 1,
        "command_id": "discover-ruler-1",
        "question_id": question["question_id"],
        "revision": 0,
        "action": "discover_keepsake",
    }

def fake_component(**kwargs):
    return SimpleNamespace(
        command=st.session_state.pop("_test_dual_clock_command", None)
    )

st.session_state["game_player_name"] = "北辰"
st.session_state["cash_case_stage"] = "practice"
st.session_state.setdefault("cash_case_attempt_index", 0)
app.render_cash_dual_clock_game = fake_component
app.render_game_hub_page()
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    assert app_test.session_state["cash_dual_clock_phase"] == "routes"
    assert app_test.session_state["cash_dual_clock_revision"] == 0
    assert app_test.session_state["cash_game_pending_keepsakes"] == [
        "brass_timeline_ruler"
    ]
    feedback = app_test.session_state["_wfz_cash_dual_clock_feedback"]
    assert feedback["title"] == "物品栏新增｜双轨校准尺"


def test_dual_clock_toolbar_go_back_stays_inside_scene_three() -> None:
    """Back from hypothesis returns to routes without leaving the game scene."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from types import SimpleNamespace
from src import app
from src.cash_case_game import build_cash_timing_question

question = build_cash_timing_question(0)
accepted_routes = {
    "contract_signed": "neither",
    "service_completed": "profit",
    "expense_incurred": "profit",
    "expense_paid": "cash",
    "cash_collected": "cash",
    "future_payment_plan": "neither",
}
if "_test_toolbar_seeded" not in st.session_state:
    st.session_state["_test_toolbar_seeded"] = True
    st.session_state["cash_dual_clock_version"] = 1
    st.session_state["cash_dual_clock_revision"] = 1
    st.session_state["cash_dual_clock_phase"] = "hypothesis"
    st.session_state["cash_clock_assignment_unlocked"] = True
    st.session_state["_wfz_cash_dual_clock_placements_routes"] = accepted_routes
    st.session_state["_wfz_cash_dual_clock_last_command_id"] = "finance-ack-1"
    st.session_state["_test_dual_clock_command"] = {
        "schema_version": 1,
        "command_id": "toolbar-back-1",
        "question_id": question["question_id"],
        "revision": 1,
        "action": "go_back",
    }

def fake_component(**kwargs):
    st.session_state["_test_dual_clock_state"] = kwargs["state"]
    return SimpleNamespace(
        command=st.session_state.pop("_test_dual_clock_command", None)
    )

st.session_state["game_player_name"] = "北辰"
st.session_state["cash_case_stage"] = "practice"
st.session_state.setdefault("cash_case_attempt_index", 0)
app.render_cash_dual_clock_game = fake_component
app.render_game_hub_page()
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    assert app_test.session_state["cash_case_stage"] == "practice"
    assert app_test.session_state["cash_dual_clock_phase"] == "routes"
    assert app_test.session_state["cash_dual_clock_revision"] == 2
    assert app_test.session_state[
        "_wfz_cash_dual_clock_placements_routes"
    ] == {
        "contract_signed": "neither",
        "service_completed": "profit",
        "expense_incurred": "profit",
        "expense_paid": "cash",
        "cash_collected": "cash",
        "future_payment_plan": "neither",
    }
    assert app_test.session_state[
        "_wfz_cash_dual_clock_last_command_id"
    ] == "finance-ack-1"
    assert app_test.session_state[
        "_wfz_cash_dual_clock_last_ui_command_id"
    ] == "toolbar-back-1"
    assert app_test.session_state[
        "_wfz_cash_dual_clock_draft_status"
    ] == "preserve"
    assert app_test.session_state["_test_dual_clock_state"]["phase"] == (
        "routes"
    )


def test_dual_clock_toolbar_rename_opens_overlay_and_preserves_draft() -> None:
    """Rename is a reversible overlay and must not acknowledge away a draft."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from types import SimpleNamespace
from src import app
from src.cash_case_game import build_cash_timing_question

question = build_cash_timing_question(0)
hypothesis_draft = {"profit-cash-gap": "receivable_pending"}
if "_test_toolbar_seeded" not in st.session_state:
    st.session_state["_test_toolbar_seeded"] = True
    st.session_state["cash_dual_clock_version"] = 1
    st.session_state["cash_dual_clock_revision"] = 1
    st.session_state["cash_dual_clock_phase"] = "hypothesis"
    st.session_state["cash_clock_assignment_unlocked"] = True
    st.session_state["_wfz_cash_dual_clock_placements_hypothesis"] = (
        hypothesis_draft
    )
    st.session_state["_wfz_cash_dual_clock_last_command_id"] = "finance-ack-2"
    st.session_state["_test_dual_clock_command"] = {
        "schema_version": 1,
        "command_id": "toolbar-rename-1",
        "question_id": question["question_id"],
        "revision": 1,
        "action": "rename_player",
    }

def fake_component(**kwargs):
    return SimpleNamespace(
        command=st.session_state.pop("_test_dual_clock_command", None)
    )

st.session_state["game_player_name"] = "北辰"
st.session_state["cash_case_stage"] = "practice"
st.session_state.setdefault("cash_case_attempt_index", 0)
app.render_cash_dual_clock_game = fake_component
app.render_game_hub_page()
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    assert app_test.session_state["_wfz_cash_game_overlay"] == "rename"
    assert app_test.session_state["cash_case_stage"] == "practice"
    assert app_test.session_state["cash_dual_clock_phase"] == "hypothesis"
    assert app_test.session_state["cash_dual_clock_revision"] == 1
    assert app_test.session_state[
        "_wfz_cash_dual_clock_placements_hypothesis"
    ] == {"profit-cash-gap": "receivable_pending"}
    assert app_test.session_state[
        "_wfz_cash_dual_clock_last_command_id"
    ] == "finance-ack-2"
    assert app_test.session_state[
        "_wfz_cash_dual_clock_draft_status"
    ] == "preserve"
    assert any(
        item.label == "新的调查员代号" for item in app_test.text_input
    )


def test_dual_clock_toolbar_restart_opens_confirmation_without_reset() -> None:
    """Restart must show the existing choice overlay before clearing progress."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from types import SimpleNamespace
from src import app
from src.cash_case_game import build_cash_timing_question

question = build_cash_timing_question(0)
orders_draft = {"contract_acceptance": "income_boundary"}
if "_test_toolbar_seeded" not in st.session_state:
    st.session_state["_test_toolbar_seeded"] = True
    st.session_state["cash_dual_clock_version"] = 1
    st.session_state["cash_dual_clock_revision"] = 2
    st.session_state["cash_dual_clock_phase"] = "orders"
    st.session_state["cash_clock_assignment_unlocked"] = True
    st.session_state["cash_gap_hypothesis_unlocked"] = True
    st.session_state["_wfz_cash_dual_clock_placements_orders"] = orders_draft
    st.session_state["_test_dual_clock_command"] = {
        "schema_version": 1,
        "command_id": "toolbar-restart-1",
        "question_id": question["question_id"],
        "revision": 2,
        "action": "restart_game",
    }

def fake_component(**kwargs):
    return SimpleNamespace(
        command=st.session_state.pop("_test_dual_clock_command", None)
    )

st.session_state["game_player_name"] = "北辰"
st.session_state["cash_case_stage"] = "practice"
st.session_state.setdefault("cash_case_attempt_index", 0)
app.render_cash_dual_clock_game = fake_component
app.render_game_hub_page()
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    assert app_test.session_state["_wfz_cash_game_overlay"] == "reset"
    assert app_test.session_state["cash_case_stage"] == "practice"
    assert app_test.session_state["cash_dual_clock_phase"] == "orders"
    assert app_test.session_state["cash_dual_clock_revision"] == 2
    assert app_test.session_state[
        "_wfz_cash_dual_clock_placements_orders"
    ] == {"contract_acceptance": "income_boundary"}
    button_labels = [item.label for item in app_test.button]
    assert "保留代号｜从教学重新开始" in button_labels
    assert "清除代号｜返回取名页" in button_labels


def test_dual_clock_toolbar_exit_routes_home_without_resetting_scene() -> None:
    """Exit hands off to home while leaving the resumable scene untouched."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from types import SimpleNamespace
from src import app
from src.cash_case_game import build_cash_timing_question

question = build_cash_timing_question(0)
route_draft = {"contract_signed": "neither"}
if "_test_toolbar_seeded" not in st.session_state:
    st.session_state["_test_toolbar_seeded"] = True
    st.session_state["cash_dual_clock_version"] = 1
    st.session_state["cash_dual_clock_revision"] = 0
    st.session_state["cash_dual_clock_phase"] = "routes"
    st.session_state["_wfz_cash_dual_clock_placements_routes"] = route_draft
    st.session_state["_test_dual_clock_command"] = {
        "schema_version": 1,
        "command_id": "toolbar-exit-1",
        "question_id": question["question_id"],
        "revision": 0,
        "action": "exit_game",
    }

def fake_component(**kwargs):
    return SimpleNamespace(
        command=st.session_state.pop("_test_dual_clock_command", None)
    )

st.session_state["game_player_name"] = "北辰"
st.session_state["cash_case_stage"] = "practice"
st.session_state.setdefault("cash_case_attempt_index", 0)
app.render_cash_dual_clock_game = fake_component
app._switch_page = lambda name: st.session_state.__setitem__(
    "_test_target_page", name
)
app.render_game_hub_page()
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    assert app_test.session_state["_test_target_page"] == "home"
    assert app_test.session_state["cash_case_stage"] == "practice"
    assert app_test.session_state["cash_dual_clock_phase"] == "routes"
    assert app_test.session_state["cash_dual_clock_revision"] == 0
    assert app_test.session_state[
        "_wfz_cash_dual_clock_placements_routes"
    ] == {"contract_signed": "neither"}
    assert app_test.session_state[
        "_wfz_cash_dual_clock_draft_status"
    ] == "preserve"


def test_office_search_requires_all_six_documents_before_reading() -> None:
    """The spatial component discovers only server-mapped office documents."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from types import SimpleNamespace
from src import app

def fake_component(**kwargs):
    st.session_state["_test_office_state"] = kwargs["state"]
    st.session_state["_test_office_question_id"] = kwargs["question_id"]
    st.session_state["_test_office_revision"] = kwargs["revision"]
    return SimpleNamespace(
        command=st.session_state.pop("_test_office_command", None)
    )

st.session_state["game_player_name"] = "北辰"
st.session_state.setdefault("cash_case_stage", "investigation")
st.session_state.setdefault("cash_evidence_attempt_index", 0)
st.session_state.setdefault("cash_discovered_document_ids", [])
app.render_cash_office_search = fake_component
app.render_game_hub_page()
"""
    app_test = AppTest.from_string(script).run()
    assert not app_test.exception
    first_state = app_test.session_state["_test_office_state"]
    assert first_state["count"] == 0
    assert first_state["required_count"] == 6
    assert first_state["search_complete"] is False
    assert len(first_state["locations"]) == 8
    assert first_state["discovered_documents"] == []
    assert all(
        "document_id" not in location
        for location in first_state["locations"]
        if location["status"] == "unsearched"
    )
    assert [
        order["id"] for order in first_state["handoff"]["orders"]
    ] == [
        "income_boundary",
        "receivable_existence",
        "subsequent_cash",
    ]

    question_id = app_test.session_state["_test_office_question_id"]
    for command_index, location_id in enumerate(
        (
            "meeting_projection",
            "locked_contract_cabinet",
            "tea_room_phone",
            "printer_output_tray",
            "finance_shared_drive",
            "shredder_archive_bag",
        ),
        start=1,
    ):
        app_test.session_state["_test_office_command"] = {
            "schema_version": 1,
            "command_id": f"office-discover-{command_index}",
            "question_id": question_id,
            "revision": app_test.session_state[
                "cash_office_search_revision"
            ],
            "action": "discover_location",
            "location_id": location_id,
        }
        app_test.run()
        assert not app_test.exception

    assert len(app_test.session_state["cash_discovered_document_ids"]) == 6
    complete_state = app_test.session_state["_test_office_state"]
    assert complete_state["count"] == 6
    assert complete_state["search_complete"] is True
    assert len(complete_state["discovered_documents"]) == 6
    app_test.session_state["_test_office_command"] = {
        "schema_version": 1,
        "command_id": "office-finish-1",
        "question_id": question_id,
        "revision": app_test.session_state["cash_office_search_revision"],
        "action": "finish_search",
    }
    app_test.run()
    assert not app_test.exception
    assert app_test.session_state["cash_case_stage"] == "reading"


def test_office_award_keepsake_survives_decoy_search_and_stage_exit() -> None:
    """The crystal's second interaction must reach the Stage 4 inventory."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from types import SimpleNamespace
from src import app

def fake_component(**kwargs):
    st.session_state["_test_office_state"] = kwargs["state"]
    st.session_state["_test_office_question_id"] = kwargs["question_id"]
    return SimpleNamespace(
        command=st.session_state.pop("_test_office_command", None)
    )

st.session_state["game_player_name"] = "北辰"
st.session_state.setdefault("cash_case_stage", "investigation")
st.session_state.setdefault("cash_evidence_attempt_index", 0)
st.session_state.setdefault("cash_discovered_document_ids", [])
app.render_cash_office_search = fake_component
app.render_game_hub_page()
"""
    app_test = AppTest.from_string(script).run()
    assert not app_test.exception
    question_id = app_test.session_state["_test_office_question_id"]

    app_test.session_state["_test_office_command"] = {
        "schema_version": 1,
        "command_id": "office-crystal-decoy-1",
        "question_id": question_id,
        "revision": 0,
        "action": "discover_location",
        "location_id": "crystal_award",
    }
    app_test.run()
    assert not app_test.exception
    assert next(
        location
        for location in app_test.session_state["_test_office_state"][
            "locations"
        ]
        if location["id"] == "crystal_award"
    )["status"] == "decoy"

    app_test.session_state["_test_office_command"] = {
        "schema_version": 1,
        "command_id": "office-crystal-keepsake-1",
        "question_id": question_id,
        "revision": 1,
        "action": "discover_keepsake",
    }
    app_test.run()
    assert not app_test.exception
    assert app_test.session_state["cash_game_pending_keepsakes"] == [
        "frosted_lens"
    ]
    assert app_test.session_state["_test_office_state"][
        "keepsake_discovered"
    ] is True

    for command_index, location_id in enumerate(
        (
            "meeting_projection",
            "locked_contract_cabinet",
            "tea_room_phone",
            "printer_output_tray",
            "finance_shared_drive",
            "shredder_archive_bag",
        ),
        start=2,
    ):
        app_test.session_state["_test_office_command"] = {
            "schema_version": 1,
            "command_id": f"office-after-keepsake-{command_index}",
            "question_id": question_id,
            "revision": app_test.session_state[
                "cash_office_search_revision"
            ],
            "action": "discover_location",
            "location_id": location_id,
        }
        app_test.run()
        assert not app_test.exception

    app_test.session_state["_test_office_command"] = {
        "schema_version": 1,
        "command_id": "office-after-keepsake-finish",
        "question_id": question_id,
        "revision": app_test.session_state["cash_office_search_revision"],
        "action": "finish_search",
    }
    app_test.run()
    assert not app_test.exception
    assert app_test.session_state["cash_game_keepsakes"] == ["frosted_lens"]
    assert app_test.session_state["cash_game_pending_keepsakes"] == []
    assert app_test.session_state["_wfz_cash_game_overlay"] == "reward"


def test_office_component_cleanup_is_scoped_to_its_own_render() -> None:
    """An old v2 cleanup must never cancel the next scene's listeners."""
    source = Path("src/static/cash-office-search-game.js").read_text(
        encoding="utf-8"
    )

    assert "const cleanup = () =>" in source
    assert "if (root.__officeSearchCleanup === cleanup)" in source
    assert (
        "return () => {\n    root.__officeSearchCleanup?.();"
        not in source
    )


def test_office_search_toolbar_back_preserves_discovered_documents() -> None:
    """The full-screen back control returns to Stage 3 without erasing work."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from types import SimpleNamespace
from src import app
from src.cash_case_game import build_cash_evidence_case

evidence_case = build_cash_evidence_case(0)
if "_test_office_toolbar_seeded" not in st.session_state:
    st.session_state["_test_office_toolbar_seeded"] = True
    st.session_state["cash_discovered_document_ids"] = ["contract_clause"]
    st.session_state["_test_office_command"] = {
        "schema_version": 1,
        "command_id": "office-back-1",
        "question_id": f"cash-office-search:{evidence_case['case_id']}",
        "revision": 1,
        "action": "go_back",
    }

def fake_component(**kwargs):
    return SimpleNamespace(
        command=st.session_state.pop("_test_office_command", None)
    )

st.session_state["game_player_name"] = "北辰"
st.session_state.setdefault("cash_case_stage", "investigation")
st.session_state.setdefault("cash_evidence_attempt_index", 0)
app.render_cash_office_search = fake_component
app.render_game_hub_page()
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    assert app_test.session_state["cash_case_stage"] == "practice"
    assert app_test.session_state["cash_discovered_document_ids"] == [
        "contract_clause"
    ]
    assert app_test.session_state[
        "_wfz_cash_office_search_draft_status"
    ] == "preserve"


def test_office_search_toolbar_rename_preserves_discovered_documents() -> None:
    """Rename opens the shared overlay while leaving Stage 4 progress intact."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from types import SimpleNamespace
from src import app
from src.cash_case_game import build_cash_evidence_case

evidence_case = build_cash_evidence_case(0)
if "_test_office_toolbar_seeded" not in st.session_state:
    st.session_state["_test_office_toolbar_seeded"] = True
    st.session_state["cash_discovered_document_ids"] = ["contract_clause"]
    st.session_state["_test_office_command"] = {
        "schema_version": 1,
        "command_id": "office-rename-1",
        "question_id": f"cash-office-search:{evidence_case['case_id']}",
        "revision": 1,
        "action": "rename_player",
    }

def fake_component(**kwargs):
    return SimpleNamespace(
        command=st.session_state.pop("_test_office_command", None)
    )

st.session_state["game_player_name"] = "北辰"
st.session_state.setdefault("cash_case_stage", "investigation")
st.session_state.setdefault("cash_evidence_attempt_index", 0)
app.render_cash_office_search = fake_component
app.render_game_hub_page()
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    assert app_test.session_state["cash_case_stage"] == "investigation"
    assert app_test.session_state["_wfz_cash_game_overlay"] == "rename"
    assert app_test.session_state["cash_discovered_document_ids"] == [
        "contract_clause"
    ]
    assert app_test.session_state[
        "_wfz_cash_office_search_draft_status"
    ] == "preserve"
    assert any(item.label == "新的调查员代号" for item in app_test.text_input)


def test_evidence_lab_completes_three_phases_without_research_file_reset() -> None:
    """The continuous lab advances only after each server-verified phase."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from types import SimpleNamespace
from src import app
from src.cash_case_game import build_cash_evidence_case

evidence_case = build_cash_evidence_case(0)

def fake_component(**kwargs):
    st.session_state["_test_lab_state"] = kwargs["state"]
    st.session_state["_test_lab_task_id"] = kwargs["task_id"]
    st.session_state["_test_lab_revision"] = kwargs["revision"]
    return SimpleNamespace(
        command=st.session_state.pop("_test_lab_command", None)
    )

st.session_state["game_player_name"] = "北辰"
st.session_state.setdefault("cash_case_stage", "reading")
st.session_state.setdefault("cash_evidence_attempt_index", 0)
st.session_state.setdefault(
    "cash_discovered_document_ids",
    [item["document_id"] for item in evidence_case["documents"]],
)
app.render_cash_evidence_lab = fake_component
app.render_game_hub_page()
"""
    app_test = AppTest.from_string(script).run(timeout=10)

    assert not app_test.exception
    task_id = app_test.session_state["_test_lab_task_id"]
    task = app_test.session_state["_test_lab_state"]["task"]
    document_ids = [
        item["document_id"] for item in task["reading"]["documents"]
    ]
    app_test.session_state["_test_lab_command"] = {
        "schema_version": 1,
        "command_id": "lab-reading-complete-1",
        "task_id": task_id,
        "revision": 0,
        "action": "submit_reading",
        "viewed_document_ids": document_ids,
        "marked_field_ids": [
            "contract_reference",
            "contract_payment_window",
            "acceptance_date",
            "acceptance_external_seal",
            "ar_year_end_balance",
            "ar_due_status",
            "receipt_date",
            "receipt_bank_match",
        ],
    }
    app_test.run(timeout=10)

    assert not app_test.exception
    assert app_test.session_state["cash_case_stage"] == "cross_check"
    assert app_test.session_state["cash_evidence_lab_phase"] == (
        "classification"
    )
    app_test.session_state["_test_lab_command"] = {
        "schema_version": 1,
        "command_id": "lab-classification-complete-1",
        "task_id": task_id,
        "revision": 1,
        "action": "submit_classification",
        "placements": {
            "contract_term_at_year_end": "year_end_fact",
            "signed_acceptance_before_cutoff": "year_end_fact",
            "year_end_ar_not_due": "year_end_fact",
            "later_bank_receipt": "subsequent_evidence",
            "chat_expectation": "unverified_claim",
            "management_forecast": "unverified_claim",
        },
    }
    app_test.run(timeout=10)

    assert not app_test.exception
    assert app_test.session_state["cash_case_stage"] == "evidence"
    assert app_test.session_state["cash_evidence_lab_phase"] == "chain"
    app_test.session_state["_test_lab_command"] = {
        "schema_version": 1,
        "command_id": "lab-chain-complete-1",
        "task_id": task_id,
        "revision": 2,
        "action": "submit_chain",
        "links": {
            "claim_payment_boundary": "contract_clause",
            "claim_completion_before_cutoff": "signed_acceptance",
            "claim_year_end_balance": "ar_subledger",
            "claim_later_cash": "post_period_receipt",
        },
    }
    app_test.run(timeout=10)

    assert not app_test.exception
    assert app_test.session_state["cash_case_stage"] == "defense"
    assert app_test.session_state["cash_evidence_attempt_index"] == 0
    assert len(app_test.session_state["cash_discovered_document_ids"]) == 6
    assert app_test.session_state["cash_evidence_lab_revision"] == 3
    assert app_test.session_state["cash_defense_lives"] == 3


def test_evidence_lab_wrong_card_keeps_case_and_locks_correct_work() -> None:
    """One bad placement is released without replacing the office dossier."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from types import SimpleNamespace
from src import app
from src.cash_case_game import (
    build_cash_evidence_case,
    build_cash_evidence_lab_public_task,
)

evidence_case = build_cash_evidence_case(0)
task = build_cash_evidence_lab_public_task(evidence_case)

def fake_component(**kwargs):
    st.session_state["_test_lab_state"] = kwargs["state"]
    return SimpleNamespace(
        command=st.session_state.pop("_test_lab_command", None)
    )

st.session_state["game_player_name"] = "北辰"
st.session_state.setdefault("cash_case_stage", "cross_check")
st.session_state.setdefault("cash_evidence_attempt_index", 0)
st.session_state.setdefault("cash_discovered_document_ids", [
    item["document_id"] for item in evidence_case["documents"]
])
st.session_state.setdefault("cash_evidence_lab_version", 1)
st.session_state.setdefault("cash_evidence_lab_revision", 4)
st.session_state.setdefault("cash_evidence_lab_task_id", task["task_id"])
st.session_state.setdefault("cash_evidence_lab_phase", "classification")
st.session_state.setdefault("cash_evidence_lab_reading_viewed_ids", [
    item["document_id"] for item in evidence_case["documents"]
])
st.session_state.setdefault("cash_evidence_lab_reading_accepted_ids", [])
st.session_state.setdefault("cash_evidence_lab_classification_accepted", {})
st.session_state.setdefault("cash_evidence_lab_chain_accepted", {})
st.session_state.setdefault("_test_lab_command", {
    "schema_version": 1,
    "command_id": "lab-classification-mixed-1",
    "task_id": task["task_id"],
    "revision": 4,
    "action": "submit_classification",
    "placements": {
        "contract_term_at_year_end": "year_end_fact",
        "later_bank_receipt": "year_end_fact",
    },
})
app.render_cash_evidence_lab = fake_component
app.render_game_hub_page()
"""
    app_test = AppTest.from_string(script).run(timeout=10)

    assert not app_test.exception
    assert app_test.session_state["cash_case_stage"] == "cross_check"
    assert app_test.session_state["cash_evidence_attempt_index"] == 0
    assert len(app_test.session_state["cash_discovered_document_ids"]) == 6
    assert app_test.session_state[
        "cash_evidence_lab_classification_accepted"
    ] == {"contract_term_at_year_end": "year_end_fact"}
    evaluation = app_test.session_state[
        "_wfz_cash_evidence_lab_evaluation"
    ]
    assert evaluation["accepted"] == ["contract_term_at_year_end"]
    assert evaluation["rejected"] == ["later_bank_receipt"]
    assert evaluation["command_id"] == "lab-classification-mixed-1"


def test_evidence_lab_back_and_legacy_migration_preserve_case_materials() -> None:
    """Old Stage 6 cannot skip v2; internal back keeps accepted progress."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from types import SimpleNamespace
from src import app
from src.cash_case_game import (
    build_cash_evidence_case,
    build_cash_evidence_lab_public_task,
)

evidence_case = build_cash_evidence_case(0)
task = build_cash_evidence_lab_public_task(evidence_case)

def fake_component(**kwargs):
    st.session_state["_test_lab_state"] = kwargs["state"]
    return SimpleNamespace(
        command=st.session_state.pop("_test_lab_command", None)
    )

st.session_state["game_player_name"] = "北辰"
st.session_state.setdefault("cash_case_stage", "cross_check")
st.session_state.setdefault("cash_evidence_attempt_index", 0)
st.session_state.setdefault(
    "cash_discovered_document_ids",
    [item["document_id"] for item in evidence_case["documents"]],
)
app.render_cash_evidence_lab = fake_component
app.render_game_hub_page()
"""
    app_test = AppTest.from_string(script).run(timeout=10)

    assert not app_test.exception
    assert app_test.session_state["cash_case_stage"] == "reading"
    assert app_test.session_state["cash_evidence_lab_phase"] == "reading"
    task_id = app_test.session_state["_test_lab_state"]["task"]["task_id"]
    app_test.session_state["cash_case_stage"] = "cross_check"
    app_test.session_state["cash_evidence_lab_phase"] = "classification"
    app_test.session_state["cash_evidence_lab_revision"] = 5
    app_test.session_state[
        "cash_evidence_lab_classification_accepted"
    ] = {"contract_term_at_year_end": "year_end_fact"}
    app_test.session_state["_test_lab_command"] = {
        "schema_version": 1,
        "command_id": "lab-back-1",
        "task_id": task_id,
        "revision": 5,
        "action": "go_back",
    }
    app_test.run(timeout=10)

    assert not app_test.exception
    assert app_test.session_state["cash_case_stage"] == "reading"
    assert app_test.session_state["cash_evidence_lab_phase"] == "reading"
    assert app_test.session_state["cash_evidence_lab_revision"] == 6
    assert app_test.session_state[
        "cash_evidence_lab_classification_accepted"
    ] == {"contract_term_at_year_end": "year_end_fact"}
    assert len(app_test.session_state["cash_discovered_document_ids"]) == 6


def test_evidence_lab_rename_opens_overlay_without_clearing_progress() -> None:
    """The component toolbar reuses the shared safe rename overlay."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from types import SimpleNamespace
from src import app
from src.cash_case_game import (
    build_cash_evidence_case,
    build_cash_evidence_lab_public_task,
)

evidence_case = build_cash_evidence_case(0)
task = build_cash_evidence_lab_public_task(evidence_case)

def fake_component(**kwargs):
    return SimpleNamespace(
        command=st.session_state.pop("_test_lab_command", None)
    )

st.session_state["game_player_name"] = "北辰"
st.session_state["cash_case_stage"] = "reading"
st.session_state["cash_evidence_attempt_index"] = 0
st.session_state["cash_discovered_document_ids"] = [
    item["document_id"] for item in evidence_case["documents"]
]
st.session_state["cash_evidence_lab_version"] = 1
st.session_state["cash_evidence_lab_revision"] = 2
st.session_state["cash_evidence_lab_task_id"] = task["task_id"]
st.session_state["cash_evidence_lab_phase"] = "reading"
st.session_state["cash_evidence_lab_reading_viewed_ids"] = [
    "contract_clause"
]
st.session_state["cash_evidence_lab_reading_accepted_ids"] = [
    "contract_reference"
]
st.session_state["cash_evidence_lab_classification_accepted"] = {}
st.session_state["cash_evidence_lab_chain_accepted"] = {}
st.session_state.setdefault("_test_lab_command", {
    "schema_version": 1,
    "command_id": "lab-rename-1",
    "task_id": task["task_id"],
    "revision": 2,
    "action": "rename_player",
})
app.render_cash_evidence_lab = fake_component
app.render_game_hub_page()
"""
    app_test = AppTest.from_string(script).run(timeout=10)

    assert not app_test.exception
    assert app_test.session_state["cash_case_stage"] == "reading"
    assert app_test.session_state["_wfz_cash_game_overlay"] == "rename"
    assert app_test.session_state[
        "cash_evidence_lab_reading_accepted_ids"
    ] == ["contract_reference"]
    assert any(item.label == "新的调查员代号" for item in app_test.text_input)


def test_cash_defense_wrong_answer_costs_life_and_changes_case() -> None:
    """A rejected seat costs one life and replaces only Stage 8's challenge."""
    from streamlit.testing.v1 import AppTest

    from src.cash_case_game import evaluate_cash_defense_committee

    script = """
import streamlit as st
from types import SimpleNamespace
from src import app

def fake_component(**kwargs):
    st.session_state["_test_committee_state"] = kwargs["state"]
    st.session_state["_test_committee_task"] = kwargs["state"]["task"]
    st.session_state["_test_committee_revision"] = kwargs["revision"]
    return SimpleNamespace(
        command=st.session_state.pop("_test_committee_command", None)
    )

st.session_state["game_player_name"] = "北辰"
st.session_state.setdefault("cash_case_stage", "defense")
st.session_state.setdefault("cash_evidence_attempt_index", 4)
st.session_state.setdefault("cash_defense_lives", 2)
st.session_state.setdefault("cash_defense_round_index", 1)
st.session_state.setdefault("cash_defense_attempt_index", 5)
app.render_cash_defense_committee = fake_component
app.render_game_hub_page()
"""
    app_test = AppTest.from_string(script).run(timeout=10)

    assert not app_test.exception
    # Legacy radio progress cannot bypass the redesigned interaction.
    assert app_test.session_state["cash_defense_committee_version"] == 1
    assert app_test.session_state["cash_defense_round_index"] == 0
    assert app_test.session_state["cash_defense_attempt_index"] == 0
    assert app_test.session_state["cash_defense_lives"] == 3
    task = app_test.session_state["_test_committee_task"]
    first_task_id = task["task_id"]
    conclusion = next(
        seat
        for seat in task["seats"]
        if seat["seat_id"] == "conclusion_strength"
    )
    wrong_card = next(
        card["card_id"]
        for card in conclusion["cards"]
        if evaluate_cash_defense_committee(
            0,
            0,
            {
                "schema_version": 1,
                "command_id": "probe-wrong-seat",
                "task_id": first_task_id,
                "revision": 0,
                "action": "submit_committee_statement",
                "placements": {
                    "conclusion_strength": card["card_id"]
                },
            },
            0,
        )["rejected"]
    )
    app_test.session_state["_test_committee_command"] = {
        "schema_version": 1,
        "command_id": "committee-wrong-1",
        "task_id": first_task_id,
        "revision": 0,
        "action": "submit_committee_statement",
        "placements": {"conclusion_strength": wrong_card},
    }
    app_test.run(timeout=10)

    assert not app_test.exception
    assert app_test.session_state["cash_defense_lives"] == 2
    assert app_test.session_state["cash_defense_attempt_index"] == 1
    assert app_test.session_state["cash_defense_round_index"] == 0
    assert app_test.session_state["cash_case_stage"] == "defense"
    assert app_test.session_state["cash_evidence_attempt_index"] == 4
    assert app_test.session_state["_test_committee_task"]["task_id"] != (
        first_task_id
    )

    # Pass the replacement challenge and verify that the next formal round
    # does not recycle the dossier the player has just solved.  The rules use
    # ``round_index + challenge_index`` to choose a scenario, so resetting the
    # challenge to zero here would repeat Round 0/challenge 1 in Round 1.
    replacement_task = app_test.session_state["_test_committee_task"]
    replacement_revision = app_test.session_state[
        "cash_defense_committee_revision"
    ]
    replacement_placements = {}
    for seat in replacement_task["seats"]:
        seat_id = seat["seat_id"]
        replacement_placements[seat_id] = next(
            card["card_id"]
            for card in seat["cards"]
            if seat_id in evaluate_cash_defense_committee(
                0,
                1,
                {
                    "schema_version": 1,
                    "command_id": f"probe-replacement-{seat_id}",
                    "task_id": replacement_task["task_id"],
                    "revision": replacement_revision,
                    "action": "submit_committee_statement",
                    "placements": {seat_id: card["card_id"]},
                },
                replacement_revision,
            )["accepted"]
        )
    app_test.session_state["_test_committee_command"] = {
        "schema_version": 1,
        "command_id": "committee-pass-replacement-1",
        "task_id": replacement_task["task_id"],
        "revision": replacement_revision,
        "action": "submit_committee_statement",
        "placements": replacement_placements,
    }
    app_test.run(timeout=10)

    assert not app_test.exception
    assert app_test.session_state["cash_defense_round_index"] == 1
    assert app_test.session_state["cash_defense_attempt_index"] == 2
    next_round_task = app_test.session_state["_test_committee_task"]
    assert next_round_task["scenario_type"] != (
        replacement_task["scenario_type"]
    )


def test_cash_defense_three_failures_restart_only_current_hearing() -> None:
    """Three failures restart only the hearing, never the evidence file."""
    from streamlit.testing.v1 import AppTest

    from src.cash_case_game import evaluate_cash_defense_committee

    script = """
import streamlit as st
from types import SimpleNamespace
from src import app

def fake_component(**kwargs):
    st.session_state["_test_committee_task"] = kwargs["state"]["task"]
    return SimpleNamespace(
        command=st.session_state.pop("_test_committee_command", None)
    )

st.session_state["game_player_name"] = "北辰"
st.session_state.setdefault("cash_case_stage", "defense")
st.session_state.setdefault("cash_defense_committee_version", 1)
st.session_state.setdefault("cash_defense_committee_revision", 0)
st.session_state.setdefault("cash_defense_lives", 3)
st.session_state.setdefault("cash_defense_round_index", 1)
st.session_state.setdefault("cash_defense_attempt_index", 0)
st.session_state.setdefault("cash_defense_completed_explanations", ["首轮通过"])
st.session_state.setdefault("cash_evidence_attempt_index", 7)
app.render_cash_defense_committee = fake_component
app.render_game_hub_page()
"""
    app_test = AppTest.from_string(script).run(timeout=10)
    for challenge_index in range(3):
        task = app_test.session_state["_test_committee_task"]
        conclusion = next(
            seat
            for seat in task["seats"]
            if seat["seat_id"] == "conclusion_strength"
        )
        revision = app_test.session_state[
            "cash_defense_committee_revision"
        ]
        wrong_card = next(
            card["card_id"]
            for card in conclusion["cards"]
            if evaluate_cash_defense_committee(
                1,
                challenge_index,
                {
                    "schema_version": 1,
                    "command_id": f"probe-wrong-{challenge_index}",
                    "task_id": task["task_id"],
                    "revision": revision,
                    "action": "submit_committee_statement",
                    "placements": {
                        "conclusion_strength": card["card_id"]
                    },
                },
                revision,
            )["rejected"]
        )
        app_test.session_state["_test_committee_command"] = {
            "schema_version": 1,
            "command_id": f"committee-failure-{challenge_index}",
            "task_id": task["task_id"],
            "revision": revision,
            "action": "submit_committee_statement",
            "placements": {"conclusion_strength": wrong_card},
        }
        app_test.run(timeout=10)

    assert not app_test.exception
    assert app_test.session_state["cash_case_stage"] == "defense"
    assert app_test.session_state["cash_defense_lives"] == 3
    assert app_test.session_state["cash_defense_round_index"] == 1
    assert app_test.session_state["cash_defense_attempt_index"] == 3
    assert app_test.session_state["cash_evidence_attempt_index"] == 7
    assert app_test.session_state["cash_defense_completed_explanations"] == [
        "首轮通过"
    ]


def test_cash_defense_three_correct_rounds_unlock_historical_mission() -> None:
    """Passing conclusion, boundary and action rounds should complete the case."""
    from streamlit.testing.v1 import AppTest

    from src.cash_case_game import evaluate_cash_defense_committee

    script = """
import streamlit as st
from types import SimpleNamespace
from src import app

def fake_component(**kwargs):
    st.session_state["_test_committee_task"] = kwargs["state"]["task"]
    return SimpleNamespace(
        command=st.session_state.pop("_test_committee_command", None)
    )

st.session_state["game_player_name"] = "北辰"
st.session_state.setdefault("cash_case_stage", "defense")
st.session_state.setdefault("cash_defense_committee_version", 1)
st.session_state.setdefault("cash_defense_committee_revision", 0)
st.session_state.setdefault("cash_defense_lives", 3)
st.session_state.setdefault("cash_defense_round_index", 0)
st.session_state.setdefault("cash_defense_attempt_index", 0)
st.session_state.setdefault("cash_defense_completed_explanations", [])
app.render_cash_defense_committee = fake_component
app.render_game_hub_page()
"""
    app_test = AppTest.from_string(script).run(timeout=10)

    for round_index in range(3):
        task = app_test.session_state["_test_committee_task"]
        challenge_index = app_test.session_state[
            "cash_defense_attempt_index"
        ]
        revision = app_test.session_state[
            "cash_defense_committee_revision"
        ]
        placements = {}
        for seat in task["seats"]:
            seat_id = seat["seat_id"]
            placements[seat_id] = next(
                card["card_id"]
                for card in seat["cards"]
                if seat_id in evaluate_cash_defense_committee(
                    round_index,
                    challenge_index,
                    {
                        "schema_version": 1,
                        "command_id": f"probe-{round_index}-{seat_id}",
                        "task_id": task["task_id"],
                        "revision": revision,
                        "action": "submit_committee_statement",
                        "placements": {seat_id: card["card_id"]},
                    },
                    revision,
                )["accepted"]
            )
        app_test.session_state["_test_committee_command"] = {
            "schema_version": 1,
            "command_id": f"committee-complete-{round_index}",
            "task_id": task["task_id"],
            "revision": revision,
            "action": "submit_committee_statement",
            "placements": placements,
        }
        app_test.run(timeout=10)

    assert not app_test.exception
    assert app_test.session_state["cash_case_stage"] == "case_completed"
    assert app_test.session_state["cash_defense_lives"] == 3
    assert len(
        app_test.session_state["cash_defense_completed_explanations"]
    ) == 3
    assert any(
        item.label == "结束联合复核｜接受真实历史调查"
        for item in app_test.button
    )


def test_cash_defense_partial_acceptance_survives_rename_toolbar() -> None:
    """A correct seat stays locked when the in-component rename action opens."""
    from streamlit.testing.v1 import AppTest

    from src.cash_case_game import evaluate_cash_defense_committee

    script = """
import streamlit as st
from types import SimpleNamespace
from src import app

def fake_component(**kwargs):
    st.session_state["_test_committee_task"] = kwargs["state"]["task"]
    return SimpleNamespace(
        command=st.session_state.pop("_test_committee_command", None)
    )

st.session_state.setdefault("game_player_name", "北辰")
st.session_state.setdefault("cash_case_stage", "defense")
st.session_state.setdefault("cash_defense_committee_version", 1)
st.session_state.setdefault("cash_defense_committee_revision", 0)
st.session_state.setdefault("cash_defense_lives", 3)
st.session_state.setdefault("cash_defense_round_index", 0)
st.session_state.setdefault("cash_defense_attempt_index", 0)
st.session_state.setdefault("cash_defense_completed_explanations", [])
app.render_cash_defense_committee = fake_component
app.render_game_hub_page()
"""
    app_test = AppTest.from_string(script).run(timeout=10)
    task = app_test.session_state["_test_committee_task"]
    conclusion = next(
        seat
        for seat in task["seats"]
        if seat["seat_id"] == "conclusion_strength"
    )
    correct_card = next(
        card["card_id"]
        for card in conclusion["cards"]
        if "conclusion_strength" in evaluate_cash_defense_committee(
            0,
            0,
            {
                "schema_version": 1,
                "command_id": "probe-correct-conclusion",
                "task_id": task["task_id"],
                "revision": 0,
                "action": "submit_committee_statement",
                "placements": {
                    "conclusion_strength": card["card_id"]
                },
            },
            0,
        )["accepted"]
    )
    app_test.session_state["_test_committee_command"] = {
        "schema_version": 1,
        "command_id": "committee-partial-1",
        "task_id": task["task_id"],
        "revision": 0,
        "action": "submit_committee_statement",
        "placements": {"conclusion_strength": correct_card},
    }
    app_test.run(timeout=10)

    assert not app_test.exception
    assert app_test.session_state["cash_defense_lives"] == 3
    assert app_test.session_state[
        "cash_defense_committee_accepted_placements"
    ] == {"conclusion_strength": correct_card}
    app_test.session_state["_test_committee_command"] = {
        "schema_version": 1,
        "command_id": "committee-rename-1",
        "task_id": task["task_id"],
        "revision": 1,
        "action": "rename_player",
    }
    app_test.run(timeout=10)

    assert not app_test.exception
    assert app_test.session_state["_wfz_cash_game_overlay"] == "rename"
    assert app_test.session_state[
        "cash_defense_committee_accepted_placements"
    ] == {"conclusion_strength": correct_card}
    assert any(item.label == "新的调查员代号" for item in app_test.text_input)


def test_cash_defense_keepsake_and_back_stay_inside_existing_case() -> None:
    """Stage 8 owns its keepsake and back opens the completed chain as review."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from types import SimpleNamespace
from src import app
from src.cash_case_game import (
    build_cash_evidence_case,
    build_cash_evidence_lab_public_task,
)

evidence_case = build_cash_evidence_case(0)
lab_task = build_cash_evidence_lab_public_task(evidence_case)

def fake_committee(**kwargs):
    st.session_state["_test_committee_task"] = kwargs["state"]["task"]
    return SimpleNamespace(
        command=st.session_state.pop("_test_committee_command", None)
    )

def fake_lab(**kwargs):
    return SimpleNamespace(command=None)

st.session_state.setdefault("game_player_name", "北辰")
st.session_state.setdefault("cash_case_stage", "defense")
st.session_state.setdefault("cash_defense_committee_version", 1)
st.session_state.setdefault("cash_defense_committee_revision", 0)
st.session_state.setdefault("cash_defense_lives", 2)
st.session_state.setdefault("cash_defense_round_index", 1)
st.session_state.setdefault("cash_defense_attempt_index", 2)
st.session_state.setdefault(
    "cash_defense_completed_explanations", ["首轮通过"]
)
st.session_state.setdefault("cash_evidence_attempt_index", 0)
st.session_state.setdefault("cash_discovered_document_ids", [
    item["document_id"] for item in evidence_case["documents"]
])
st.session_state.setdefault("cash_evidence_lab_version", 1)
st.session_state.setdefault("cash_evidence_lab_revision", 3)
st.session_state.setdefault("cash_evidence_lab_task_id", lab_task["task_id"])
st.session_state.setdefault("cash_evidence_lab_phase", "chain")
st.session_state.setdefault("cash_evidence_lab_reading_viewed_ids", [])
st.session_state.setdefault("cash_evidence_lab_reading_accepted_ids", [])
st.session_state.setdefault("cash_evidence_lab_classification_accepted", {})
st.session_state.setdefault("cash_evidence_lab_chain_accepted", {
    "claim_payment_boundary": "contract_clause",
    "claim_completion_before_cutoff": "signed_acceptance",
    "claim_year_end_balance": "ar_subledger",
    "claim_later_cash": "post_period_receipt",
})
app.render_cash_defense_committee = fake_committee
app.render_cash_evidence_lab = fake_lab
app.render_game_hub_page()
"""
    app_test = AppTest.from_string(script).run(timeout=10)
    task = app_test.session_state["_test_committee_task"]
    app_test.session_state["_test_committee_command"] = {
        "schema_version": 1,
        "command_id": "committee-keepsake-1",
        "task_id": task["task_id"],
        "revision": 0,
        "action": "discover_keepsake",
    }
    app_test.run(timeout=10)

    assert not app_test.exception
    assert "reverse_black_piece" in app_test.session_state[
        "cash_game_pending_keepsakes"
    ]
    app_test.session_state["_test_committee_command"] = {
        "schema_version": 1,
        "command_id": "committee-back-1",
        "task_id": task["task_id"],
        "revision": 0,
        "action": "go_back",
    }
    app_test.run(timeout=10)

    assert not app_test.exception
    assert app_test.session_state["cash_case_stage"] == "evidence"
    assert app_test.session_state[
        "_wfz_cash_evidence_lab_review_from_defense"
    ] is True
    assert app_test.session_state["cash_defense_round_index"] == 1
    assert app_test.session_state["cash_defense_attempt_index"] == 2
    assert app_test.session_state["cash_defense_lives"] == 2


def test_hidden_scene_keepsake_is_revealed_only_after_scene_completion() -> None:
    """A discovered object should wait for the scene result before revealing."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from src.app import render_game_hub_page

st.session_state["game_player_name"] = "北辰"
st.session_state["cash_case_stage"] = "briefing"
render_game_hub_page()
"""
    app_test = AppTest.from_string(script).run()
    next(item for item in app_test.button if item.label == "·").click().run()

    assert app_test.session_state["cash_game_pending_keepsakes"] == [
        "dual_dial_watch"
    ]
    assert app_test.session_state["cash_game_keepsakes"] == []

    next(
        item for item in app_test.button
        if item.label == "我已分清两只时钟｜调取业务档案"
    ).click().run()

    assert app_test.session_state["cash_game_keepsakes"] == [
        "dual_dial_watch"
    ]
    assert app_test.session_state["_wfz_cash_game_overlay"] == "reward"
    assert "双刻度怀表" in _all_rendered_markup(app_test)


def test_final_council_consumes_only_a_correctly_matched_keepsake() -> None:
    """Touch-friendly handoff should unlock the matching mentor hint once."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from src.app import render_game_hub_page

st.session_state["game_player_name"] = "北辰"
st.session_state["cash_case_stage"] = "case_completed"
st.session_state["cash_game_keepsakes"] = ["double_sided_prism"]
render_game_hub_page()
"""
    app_test = AppTest.from_string(script).run()
    next(
        item for item in app_test.selectbox
        if item.label == "从信物栏取出一件信物"
    ).set_value("◇ 双面棱镜")
    next(
        item for item in app_test.button
        if item.label == "交给 苏棱　→"
    ).click().run()

    assert app_test.session_state["cash_game_used_hints"] == [
        "double_sided_prism"
    ]
    assert "同源复述不能算交叉验证" in _all_rendered_markup(app_test)


def test_research_workspace_groups_tools_by_user_task() -> None:
    """Make the product structure understandable before opening a tool."""
    from streamlit.testing.v1 import AppTest

    script = """
from src.app import render_research_workspace_page

render_research_workspace_page()
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    workspace_markup = "\n".join(
        item.value for item in app_test.markdown
    )
    for collection_title in (
        "01｜发现研究对象",
        "02｜完成公司初研",
        "03｜调查市场事件",
        "04｜核验财务证据",
        "05｜跟踪与治理研究",
    ):
        assert collection_title in workspace_markup

    button_labels = [button.label for button in app_test.button]
    assert "运行一键综合研究" in button_labels
    assert "核验上次研究后的新证据" in button_labels
    assert "维护研究结论账本" in button_labels
    assert "调查市场异动" in button_labels
    assert "生成最新年报财务快照" in button_labels
    assert "核验年报原文与证据" in button_labels
    assert "查看方法与审计" in button_labels


def test_research_collection_config_assigns_every_tool_once() -> None:
    """Keep the research hub and sidebar driven by one unambiguous map."""
    from src.app import _RESEARCH_COLLECTIONS, _research_collection_for_page

    targets = [
        target
        for collection in _RESEARCH_COLLECTIONS
        for _, target in collection["tools"]
    ]

    assert len(_RESEARCH_COLLECTIONS) == 5
    assert len(targets) == len(set(targets))
    assert _research_collection_for_page("limit_up") == 0
    assert _research_collection_for_page("comprehensive") == 1
    assert _research_collection_for_page("historical") == 2
    assert _research_collection_for_page("annual") == 3
    assert _research_collection_for_page("thesis_ledger") == 4
    assert _research_collection_for_page("game") is None


def test_research_sidebar_only_renders_inside_research_branch() -> None:
    """Do not leak the research task menu into the game or platform home."""
    from types import SimpleNamespace
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from types import SimpleNamespace
from src import app

page_names = [
    "home", "game", "workspace",
    *(
        target
        for collection in app._RESEARCH_COLLECTIONS
        for _, target in collection["tools"]
    ),
]
registry = {
    name: SimpleNamespace(url_path=name)
    for name in page_names
}
current = registry[st.session_state.get("current_page", "game")]
original_page_link = st.page_link
try:
    st.page_link = lambda page, **kwargs: st.write(kwargs["label"])
    app._render_research_sidebar_navigation(current, registry)
finally:
    st.page_link = original_page_link
"""
    game_page = AppTest.from_string(script).run()
    assert not game_page.exception
    assert "研究子任务" not in "\n".join(
        item.value for item in game_page.markdown
    )

    research_page = AppTest.from_string(script)
    research_page.session_state["current_page"] = "annual"
    research_page.run()
    assert not research_page.exception
    research_markup = "\n".join(
        item.value for item in research_page.markdown
    )
    assert "研究子任务" in research_markup
    assert "返回研究中枢总览" in research_markup
    assert next(
        expander
        for expander in research_page.expander
        if expander.label == "核验财务证据"
    ).proto.expanded


def test_evidence_delta_page_starts_without_live_requests() -> None:
    """Keep the new continuity workflow explicit before a user runs it."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from src.app import render_evidence_delta_page

st.session_state["selected_company"] = {
    "code": "600519",
    "name": "贵州茅台",
    "exchange": "SH",
    "exchange_name": "上海证券交易所",
    "canonical_code": "600519.SH",
}
render_evidence_delta_page()
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    assert any(
        button.label == "核验上次研究后的官方证据"
        for button in app_test.button
    )
    info_text = "\n".join(item.value for item in app_test.info)
    assert "首次运行会核验最近30天" in info_text


def test_research_thesis_page_starts_without_live_requests() -> None:
    """Keep hypothesis creation explicit and human-reviewed."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from src.app import render_research_thesis_page

company = {
    "code": "600519",
    "name": "贵州茅台",
    "exchange": "SH",
    "exchange_name": "上海证券交易所",
    "canonical_code": "600519.SH",
}
st.session_state["selected_company"] = company
st.session_state["_wfz_browser_research_snapshot"] = {
    "version": 3,
    "recent": [],
    "watchlist": [],
    "evidence_checkpoints": [],
    "research_theses": [],
    "last_command_id": None,
    "storage_status": "available",
}
render_research_thesis_page()
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    page_markup = "\n".join(item.value for item in app_test.markdown)
    assert "THESIS LEDGER" in page_markup
    assert "研究结论账本" in page_markup
    assert any(
        button.label == "保存研究假设到当前浏览器"
        for button in app_test.button
    )
    assert any(
        button.label == "先去核验官方新证据"
        for button in app_test.button
    )
    assert app_test.download_button[0].disabled


def test_financial_snapshot_page_starts_without_live_requests() -> None:
    """Keep the on-demand workflow idle until the user requests a report."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from src.app import render_financial_snapshot_page

st.session_state["selected_company"] = {
    "code": "600519",
    "name": "贵州茅台",
    "exchange": "SH",
    "exchange_name": "上海证券交易所",
    "canonical_code": "600519.SH",
}
render_financial_snapshot_page()
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    page_markup = "\n".join(item.value for item in app_test.markdown)
    assert "ON-DEMAND FINANCIAL SNAPSHOT" in page_markup
    assert "全市场按需财务快照 Agent" in page_markup
    assert any(
        button.label == "生成最新年报财务快照"
        for button in app_test.button
    )
    assert "尚未生成当前公司的快照" in "\n".join(
        item.value for item in app_test.info
    )


def test_financial_snapshot_page_renders_reviewable_result() -> None:
    """Render metrics, provenance and export without retaining a source PDF."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from src.app import render_financial_snapshot_page

company = {
    "code": "600519",
    "name": "贵州茅台",
    "exchange": "SH",
    "exchange_name": "上海证券交易所",
    "canonical_code": "600519.SH",
}
metric_specs = [
    ("revenue", "营业收入", "利润表", 100),
    ("net_profit", "净利润（优先归母口径）", "利润表", 100),
    ("operating_cash_flow", "经营活动现金流量净额", "现金流量表", 102),
    ("total_assets", "资产总额", "资产负债表", 98),
    ("total_liabilities", "负债总额", "资产负债表", 98),
]
st.session_state["selected_company"] = company
st.session_state["on_demand_financial_snapshot"] = {
    "schema_version": "1.0",
    "generated_at": "2026-08-06T00:00:00+00:00",
    "status": "ready_for_human_review",
    "status_label": "自动检查完成，等待人工复核",
    "company": company,
    "report": {
        "report_year": 2025,
        "published_date": "2026-04-20",
        "title": "贵州茅台2025年年度报告",
        "source_url": "https://static.cninfo.com.cn/example.pdf",
        "page_count": 200,
    },
    "source_fingerprint_sha256": "a" * 64,
    "statement_checks": {
        "income_statement_reconciled": True,
        "balance_sheet_reconciled": True,
        "cash_flow_statement_reconciled": True,
    },
    "unit": "元",
    "unit_note": "三张报表原始单位均为“元”。",
    "metrics": [
        {
            "key": key,
            "label": label,
            "current_yuan": 10_000_000_000.0,
            "previous_yuan": 9_000_000_000.0,
            "change_rate": 1 / 9,
            "statement": statement,
            "pages": {"start": page, "end": page + 1},
        }
        for key, label, statement, page in metric_specs
    ],
    "ratios": {
        "net_profit_margin": 0.1,
        "operating_cash_conversion": 1.2,
        "liabilities_to_assets": 0.4,
    },
    "limitations": ["自动提取，等待人工复核。"],
}
render_financial_snapshot_page()
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    assert any(
        item.value == "自动检查完成，等待人工复核"
        for item in app_test.success
    )
    assert any(item.label == "营业收入" for item in app_test.metric)
    assert any(item.label == "资产负债率" for item in app_test.metric)
    assert app_test.download_button[0].label == "下载财务快照核验底稿（HTML）"
    link_buttons = app_test.get("link_button")
    assert any(
        item.proto.label == "查看官方年报原文"
        and item.proto.url == "https://static.cninfo.com.cn/example.pdf"
        for item in link_buttons
    )


def test_research_terminal_shows_device_local_recent_and_watchlist_entries() -> None:
    """Keep local research shortcuts useful without a login or database."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from src.app import render_research_terminal_page

company = {
    "code": "600519",
    "name": "贵州茅台",
    "exchange": "SH",
    "exchange_name": "上海证券交易所",
    "canonical_code": "600519.SH",
}
st.session_state["_wfz_browser_research_snapshot"] = {
    "version": 1,
    "recent": [company],
    "watchlist": [company],
    "last_command_id": None,
    "storage_status": "available",
}
render_research_terminal_page()
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    labels = [button.label for button in app_test.button]
    assert "继续研究｜贵州茅台 · 600519" in labels
    assert "★ 移出自选" in labels
    assert "研究｜贵州茅台 · 600519" in labels
    assert "移除" in labels
    captions = "\n".join(item.value for item in app_test.caption)
    assert "只保存在当前浏览器" in captions


def test_comprehensive_research_brief_renders_as_a_downloadable_page() -> None:
    """Keep the flagship Agent result stable without live provider calls."""
    from streamlit.testing.v1 import AppTest

    script = """
from datetime import date
from src.china_stock import build_company_identity
from src.comprehensive_research import build_comprehensive_research_brief
from src.app import _show_comprehensive_research_brief

brief = build_comprehensive_research_brief(
    build_company_identity("600519", "贵州茅台"),
    announcements=[],
    announcements_status="已核验公告 0 条",
    generated_on=date(2026, 8, 1),
)
_show_comprehensive_research_brief(brief)
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    assert any(
        "综合研究状态" in item.value for item in app_test.markdown
    )
    assert any(
        "当前最值得关注" in item.value for item in app_test.markdown
    )
    assert any(
        "五条证据链" in item.value for item in app_test.markdown
    )
    download_labels = [item.label for item in app_test.download_button]
    assert download_labels == [
        "下载综合研究简报（HTML）",
        "下载可审计数据包（JSON）",
    ]


def test_comprehensive_page_entry_renders_without_live_requests() -> None:
    """Show the selected company and wait for an explicit one-click run."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from src.app import render_comprehensive_research_page

st.session_state["selected_company"] = {
    "code": "600519",
    "name": "贵州茅台",
    "exchange": "SH",
    "exchange_name": "上海证券交易所",
    "canonical_code": "600519.SH",
}
render_comprehensive_research_page()
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    page_markup = "\n".join(item.value for item in app_test.markdown)
    assert "COMPREHENSIVE AGENT" in page_markup
    assert "一键综合研究 Agent" in page_markup
    assert any(
        button.label == "运行一键综合研究 Agent"
        for button in app_test.button
    )


def test_company_search_run_stores_one_matching_comprehensive_brief() -> None:
    """Turn an explicit company search into one direct research result."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from datetime import date
from src import app
from src.china_stock import build_company_identity
from src.comprehensive_research import build_comprehensive_research_brief

company = build_company_identity("600519", "贵州茅台")
st.session_state["selected_company"] = company
st.session_state[app.COMPREHENSIVE_BRIEF_KEY] = {"old": True}
st.session_state[app.COMPREHENSIVE_ELAPSED_KEY] = 999.0

def fake_run(selected_company):
    return build_comprehensive_research_brief(
        selected_company,
        announcements=[],
        announcements_status="已核验公告 0 条",
        generated_on=date(2026, 8, 11),
    )

original_run = app._run_comprehensive_research
try:
    app._run_comprehensive_research = fake_run
    app._execute_comprehensive_research(company)
    app.render_comprehensive_research_page()
finally:
    app._run_comprehensive_research = original_run
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    brief = app_test.session_state["comprehensive_research_brief"]
    assert brief["company"]["canonical_code"] == "600519.SH"
    assert app_test.session_state[
        "comprehensive_research_elapsed_seconds"
    ] < 999.0
    assert any(
        button.label == "重新运行并刷新公开数据"
        for button in app_test.button
    )
    page_markup = "\n".join(item.value for item in app_test.markdown)
    assert "当前最值得关注" in page_markup


def test_audited_company_onboarding_waits_for_explicit_discovery() -> None:
    """Keep the expansion Agent lightweight until the user starts a task."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from src.app import render_company_onboarding_page

st.session_state["selected_company"] = {
    "code": "000333",
    "name": "美的集团",
    "exchange": "SZ",
    "exchange_name": "深圳证券交易所",
    "canonical_code": "000333.SZ",
}
render_company_onboarding_page()
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    page_markup = "\n".join(item.value for item in app_test.markdown)
    assert "ONBOARDING AGENT" in page_markup
    assert "已核验公司扩展 Agent" in page_markup
    assert any(
        button.label == "发现最近三份完整年报"
        for button in app_test.button
    )
    assert not app_test.download_button


def test_audited_company_onboarding_offers_serial_batch_processing() -> None:
    """Offer one action without parallelising memory-heavy PDF work."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from src.app import render_company_onboarding_page

company = {
    "code": "000001",
    "name": "平安银行",
    "exchange": "SZ",
    "exchange_name": "深圳证券交易所",
    "canonical_code": "000001.SZ",
}
st.session_state["selected_company"] = company
st.session_state["audited_company_onboarding_state"] = {
    "canonical_code": company["canonical_code"],
    "reports": [
        {
            "report_year": year,
            "published_date": f"{year + 1}-04-20",
            "title": f"平安银行{year}年年度报告",
            "url": f"https://static.cninfo.com.cn/{year}.pdf",
        }
        for year in (2025, 2024, 2023)
    ],
    "results": {},
}
render_company_onboarding_page()
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    assert any(
        button.label == "自动串行核验全部剩余报告（3份）"
        and not button.disabled
        for button in app_test.button
    )


def test_market_radar_handoff_stores_context_and_navigates() -> None:
    """Carry the radar evidence into a fresh comprehensive-research entry."""
    from streamlit.testing.v1 import AppTest

    script = """
import streamlit as st
from src import app

company = {
    "code": "600519",
    "name": "贵州茅台",
    "exchange": "SH",
    "exchange_name": "上海证券交易所",
    "canonical_code": "600519.SH",
}
row = {
    "company": company,
    "latest_date": "2026-07-31",
    "daily_return": 0.10,
    "volume_ratio_20d": 2.5,
    "turnover": 0.04,
    "turnover_percentile_250d": 0.95,
    "limit_up_candidate": True,
    "triggered_signals": ["涨停候选", "明显放量"],
    "trigger_count": 2,
    "available_signal_count": 3,
    "radar_status": "复合异动",
    "market_source": "测试公开行情",
    "turnover_source": "测试普通换手率",
    "latest_disclosure": {
        "title": "贵州茅台2025年年度报告",
        "published_date": "2026-04-17",
        "source_url": "https://static.cninfo.com.cn/test.pdf",
        "category": "财务报告",
        "attention": "高",
        "days_old": 105,
    },
    "disclosure_status": "已核验近45日公告 1 条",
    "research_priority": "P1｜立即核查",
    "research_reasons": ["市场端同时触发2项异动证据"],
}
st.session_state["comprehensive_research_brief"] = {"old": True}
app._switch_page = lambda name: st.session_state.__setitem__(
    "test_target_page", name
)
app._handoff_market_radar_to_comprehensive(row)
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    assert app_test.session_state["selected_company"]["code"] == "600519"
    context = app_test.session_state["radar_research_context"]
    assert context["research_priority"] == "P1｜立即核查"
    assert context["triggered_signals"] == ["涨停候选", "明显放量"]
    assert context["latest_disclosure"]["title"] == (
        "贵州茅台2025年年度报告"
    )
    assert app_test.session_state["test_target_page"] == "comprehensive"
    assert "comprehensive_research_brief" not in app_test.session_state


def test_comprehensive_page_shows_only_matching_radar_context() -> None:
    """Do not leak a previous company's radar clue into another company."""
    from streamlit.testing.v1 import AppTest

    matching_script = """
import streamlit as st
from src.app import render_comprehensive_research_page

st.session_state["selected_company"] = {
    "code": "600519",
    "name": "贵州茅台",
    "exchange": "SH",
    "exchange_name": "上海证券交易所",
    "canonical_code": "600519.SH",
}
st.session_state["radar_research_context"] = {
    "canonical_code": "600519.SH",
    "scan_date": "2026-08-02",
    "market_date": "2026-07-31",
    "research_priority": "P1｜立即核查",
    "radar_status": "复合异动",
    "triggered_signals": ["涨停候选", "明显放量"],
    "research_reasons": ["市场端同时触发2项异动证据"],
    "disclosure_status": "已核验近45日公告 1 条",
    "latest_disclosure": None,
}
render_comprehensive_research_page()
"""
    matching = AppTest.from_string(matching_script).run()

    assert not matching.exception
    matching_markup = "\n".join(item.value for item in matching.markdown)
    assert "本次研究由自选股雷达触发" in matching_markup
    assert any(
        metric.label == "研究顺序" and metric.value == "P1｜立即核查"
        for metric in matching.metric
    )

    mismatched = AppTest.from_string(
        matching_script.replace(
            '"600519.SH",\n    "scan_date"',
            '"300750.SZ",\n    "scan_date"',
        )
    ).run()
    assert not mismatched.exception
    mismatched_markup = "\n".join(
        item.value for item in mismatched.markdown
    )
    assert "本次研究由自选股雷达触发" not in mismatched_markup


def test_company_code_search_skips_the_live_directory() -> None:
    """A six-digit code should resolve instantly without a full-list request."""
    from streamlit.testing.v1 import AppTest

    script = """
from datetime import date
from src import app
from src.comprehensive_research import build_comprehensive_research_brief

def fail_if_called():
    raise AssertionError("the live directory should not be requested")

def fake_run(selected_company):
    return build_comprehensive_research_brief(
        selected_company,
        announcements=[],
        announcements_status="已核验公告 0 条",
        generated_on=date(2026, 8, 11),
    )

app.load_a_share_directory = fail_if_called
original_run = app._run_comprehensive_research
try:
    app._run_comprehensive_research = fake_run
    app.render_research_terminal_page()
finally:
    app._run_comprehensive_research = original_run
"""
    app_test = AppTest.from_string(script).run()
    app_test.text_input[0].set_value("600519")
    start_button = next(
        button for button in app_test.button if button.label == "开始研究"
    )
    start_button.click().run()

    assert not app_test.exception
    selected = app_test.session_state["selected_company"]
    assert selected["canonical_code"] == "600519.SH"
    assert selected["name"] == "贵州茅台"
    brief = app_test.session_state["comprehensive_research_brief"]
    assert brief["company"]["canonical_code"] == "600519.SH"


def test_company_research_sources_start_independently(
    monkeypatch,
) -> None:
    """Market and disclosure requests should overlap without merging errors."""
    from threading import Barrier

    from src import app

    barrier = Barrier(2)
    market = pd.DataFrame({"close": [1.0]})
    announcements = pd.DataFrame({"title": ["测试公告"]})

    def fake_market(*args, **kwargs):
        barrier.wait(timeout=1)
        return market

    def fake_announcements(*args, **kwargs):
        barrier.wait(timeout=1)
        return announcements

    monkeypatch.setattr(app, "fetch_market_history", fake_market)
    monkeypatch.setattr(app, "fetch_announcements", fake_announcements)

    result = app._fetch_company_research_sources_concurrently(
        "600519",
        "2025-06-01",
        "2026-08-01",
        "qfq",
    )

    assert result[0] is market
    assert result[1] is announcements
    assert result[2:] == (None, None)


def test_parallel_company_sources_keep_a_successful_lane(
    monkeypatch,
) -> None:
    """One failed provider must not erase the independent successful lane."""
    from src import app

    announcements = pd.DataFrame({"title": ["测试公告"]})

    def fail_market(*args, **kwargs):
        raise app.DataSourceError("行情暂不可用")

    monkeypatch.setattr(app, "fetch_market_history", fail_market)
    monkeypatch.setattr(
        app,
        "fetch_announcements",
        lambda *args, **kwargs: announcements,
    )

    result = app._fetch_company_research_sources_concurrently(
        "600519",
        "2025-06-01",
        "2026-08-01",
        "qfq",
    )

    assert result[0] is None
    assert result[1] is announcements
    assert result[2] == "行情暂不可用"
    assert result[3] is None


def test_comprehensive_runner_keeps_independent_sources_auditable(
    monkeypatch,
) -> None:
    """Cover the five-lane runner while avoiding live public requests."""
    from src import app

    company = {
        "code": "600519",
        "name": "贵州茅台",
        "exchange": "SH",
        "exchange_name": "上海证券交易所",
        "canonical_code": "600519.SH",
    }
    dates = pd.date_range("2025-06-02", periods=300, freq="B")
    close = pd.Series([100 + index * 0.1 for index in range(len(dates))])
    market_frame = pd.DataFrame(
        {
            "date": dates,
            "open": close - 0.2,
            "high": close + 0.6,
            "low": close - 0.8,
            "close": close,
            "volume": [1_000_000.0] * 299 + [2_500_000.0],
            "amount": 100_000_000.0,
            "turnover": [1.0] * 299 + [4.0],
        }
    )
    market_frame.attrs["source"] = "测试公开行情"
    market_frame.attrs["turnover_source"] = "测试普通换手率"
    annual_url = (
        "https://static.cninfo.com.cn/finalpage/"
        "2026-04-01/1234567890.PDF"
    )
    announcements = pd.DataFrame(
        {
            "code": ["600519"],
            "name": ["贵州茅台"],
            "title": ["贵州茅台2025年年度报告"],
            "date": [date(2026, 4, 1)],
            "url": [annual_url],
            "category": ["财务报告"],
            "attention": ["高"],
        }
    )

    monkeypatch.setattr(
        app,
        "load_company_research_sources",
        lambda *args, **kwargs: (
            market_frame,
            announcements,
            None,
            None,
        ),
    )
    monkeypatch.setattr(
        app,
        "verified_financial_history_codes",
        lambda: (),
    )

    brief = app._run_comprehensive_research(company)

    assert brief["coverage_ratio"] == 0.8
    assert brief["verified_lane_count"] == 4
    assert brief["unavailable_lane_count"] == 1
    assert any(
        finding["category"] == "交易活跃度"
        for finding in brief["findings"]
    )
    assert any(
        lane["key"] == "annual_report"
        and lane["source_url"] == annual_url
        for lane in brief["evidence_lanes"]
    )

    app.st.session_state["on_demand_financial_snapshot"] = {
        "status": "needs_review",
        "company": company,
        "report": {
            "report_year": 2025,
            "published_date": "2026-04-01",
            "source_url": annual_url,
        },
    }
    try:
        brief_with_snapshot = app._run_comprehensive_research(company)
    finally:
        app.st.session_state.pop("on_demand_financial_snapshot", None)

    assert brief_with_snapshot["coverage_ratio"] == 0.9
    assert brief_with_snapshot["partial_lane_count"] == 1
    assert any(
        lane["key"] == "financial_history"
        and lane["label"] == "单期财务快照（待复核）"
        for lane in brief_with_snapshot["evidence_lanes"]
    )


def test_event_evidence_chain_renderer_shows_auditable_limits() -> None:
    """Render the evidence chain as real Streamlit components."""
    from streamlit.testing.v1 import AppTest

    script = """
from src.app import _show_event_evidence_chain

chain = {
    "event_date": "2026-07-20",
    "window_days": 7,
    "status": "matched",
    "matches": [{
        "source_id": "official-1",
        "title": "贵州茅台重大事项公告",
        "published_date": "2026-07-18",
        "source_type": "其他公告",
        "source_url": "https://static.cninfo.com.cn/example.pdf",
        "evidence_grade": "A",
        "days_before_event": 2,
        "relation": "此前2天公开",
    }],
    "matched_count": 1,
    "same_day_count": 0,
    "nearest_gap_days": 2,
    "future_excluded_count": 4,
    "conclusion": (
        "所选日期此前 6 天内匹配 1 条官方公告；"
        "最近一条相隔 2 天。"
    ),
    "limitation": (
        "公告与异常交易日时间接近，只能作为复盘线索，"
        "不能据此认定公告导致了价格或成交量变化。"
    ),
}
_show_event_evidence_chain(chain, event_context="明显放量")
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    assert any(
        "异动—公告证据链" in item.value for item in app_test.markdown
    )
    assert any(
        "异动类型：明显放量" in item.value for item in app_test.caption
    )
    assert any(
        "最近一条相隔 2 天" in item.value for item in app_test.success
    )
    assert any(
        "不能据此认定" in item.value for item in app_test.warning
    )
    assert any(
        "截止日后公告未进入" in item.value for item in app_test.caption
    )
    link_buttons = app_test.get("link_button")
    assert len(link_buttons) == 1
    assert link_buttons[0].proto.label == "查看原文 ↗"
    assert link_buttons[0].proto.url == (
        "https://static.cninfo.com.cn/example.pdf"
    )


def test_company_research_page_renders_a_successful_market_result(
    monkeypatch,
) -> None:
    """Keep the deployed success branch covered, including source provenance."""
    from src import app

    company = {
        "code": "600519",
        "name": "贵州茅台",
        "exchange": "SH",
        "exchange_name": "上海证券交易所",
        "canonical_code": "600519.SH",
    }
    market_frame = pd.DataFrame(
        {
            "date": [pd.Timestamp("2026-07-29")],
            "open": [1300.0],
            "high": [1325.0],
            "low": [1295.0],
            "close": [1321.0],
            "volume": [1000.0],
            "amount": [1_321_000.0],
        }
    )
    market_frame.attrs["source"] = "腾讯财经公开日线（备用源）"
    metrics = {
        "latest_date": "2026-07-29",
        "latest_close": 1321.0,
        "daily_change": 0.001,
        "return_20d": 0.107,
        "return_60d": 0.08,
        "return_250d": None,
        "annualised_volatility": 0.214,
        "max_drawdown": -0.25,
        "observations": 1,
    }

    monkeypatch.setattr(app, "apply_product_theme", lambda: None)
    monkeypatch.setattr(app, "show_compact_page_header", lambda *args: None)
    monkeypatch.setattr(app, "_selected_company", lambda: company)
    monkeypatch.setattr(app, "_show_company_banner", lambda selected: None)
    monkeypatch.setattr(
        app,
        "_load_company_research_data",
        lambda selected: (market_frame, metrics, None),
    )
    monkeypatch.setattr(app, "show_product_footer", lambda: None)

    app.render_company_research_page()


def test_market_page_passes_activity_evidence_to_the_renderer(
    monkeypatch,
) -> None:
    """Cover the K-line page integration without calling a live data source."""
    from src import app

    company = {
        "code": "600519",
        "name": "贵州茅台",
        "exchange": "SH",
        "exchange_name": "上海证券交易所",
        "canonical_code": "600519.SH",
    }
    dates = pd.date_range("2026-06-01", periods=30, freq="B")
    close = pd.Series([100 + index * 0.2 for index in range(len(dates))])
    market_frame = pd.DataFrame(
        {
            "date": dates,
            "open": close - 0.2,
            "high": close + 0.6,
            "low": close - 0.8,
            "close": close,
            "volume": [1_000_000] * 29 + [2_000_000],
            "amount": 100_000_000,
            "turnover": 2.5,
        }
    )
    market_frame.attrs["source"] = "测试公开行情"
    rendered_activity = []

    monkeypatch.setattr(app, "apply_product_theme", lambda: None)
    monkeypatch.setattr(app, "show_compact_page_header", lambda *args: None)
    monkeypatch.setattr(app, "_selected_company", lambda: company)
    monkeypatch.setattr(app, "_show_company_banner", lambda selected: None)
    monkeypatch.setattr(
        app,
        "load_a_share_history",
        lambda *args: market_frame,
    )
    monkeypatch.setattr(
        app,
        "_show_market_activity_evidence",
        lambda activity: rendered_activity.append(activity),
    )
    monkeypatch.setattr(app, "_build_kline_figure", lambda *args: object())
    monkeypatch.setattr(app.st, "plotly_chart", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "show_product_footer", lambda: None)

    app.render_market_page()

    assert rendered_activity[0]["volume_ratio_20d"] == 2
    assert rendered_activity[0]["effective_turnover"] is None


def test_volume_turnover_page_builds_a_bounded_research_snapshot(
    monkeypatch,
) -> None:
    """Cover the dedicated participation page without live providers."""
    from src import app

    company = {
        "code": "600519",
        "name": "贵州茅台",
        "exchange": "SH",
        "exchange_name": "上海证券交易所",
        "canonical_code": "600519.SH",
    }
    dates = pd.date_range("2026-04-01", periods=60, freq="B")
    close = pd.Series([100 + index * 0.1 for index in range(len(dates))])
    market_frame = pd.DataFrame(
        {
            "date": dates,
            "open": close - 0.2,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": [1_000_000.0] * 59 + [2_500_000.0],
            "amount": 100_000_000.0,
            "turnover": [1.0] * 59 + [4.0],
        }
    )
    market_frame.attrs["source"] = "测试公开行情"
    verified_snapshots = []

    monkeypatch.setattr(app, "apply_product_theme", lambda: None)
    monkeypatch.setattr(app, "show_compact_page_header", lambda *args: None)
    monkeypatch.setattr(app, "_selected_company", lambda: company)
    monkeypatch.setattr(app, "_show_company_banner", lambda selected: None)
    monkeypatch.setattr(
        app,
        "load_a_share_history",
        lambda *args: market_frame,
    )
    monkeypatch.setattr(
        app,
        "_build_volume_turnover_figure",
        lambda *args: object(),
    )
    monkeypatch.setattr(app.st, "plotly_chart", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        app,
        "_show_effective_turnover_verification",
        lambda snapshot: verified_snapshots.append(snapshot),
    )
    monkeypatch.setattr(app, "show_product_footer", lambda: None)

    app.render_volume_turnover_page()

    assert verified_snapshots[0]["volume_ratio_20d"] == 2.5
    assert verified_snapshots[0]["ordinary_turnover"] == 0.04
    assert verified_snapshots[0]["high_volume_days"] == 1


def test_market_radar_page_scans_and_ranks_a_bounded_watchlist(
    monkeypatch,
) -> None:
    """Cover the research queue without calling live market providers."""
    from src import app

    downloads = []
    dates = pd.date_range("2026-05-01", periods=30, freq="B")
    close = pd.Series([100 + index * 0.1 for index in range(len(dates))])

    def fake_history(
        code: str,
        start_date_text: str,
        end_date_text: str,
        adjust: str,
    ) -> pd.DataFrame:
        volume = [1_000_000.0] * len(dates)
        turnover = [1.0] * len(dates)
        if code == "600519":
            volume[-1] = 2_500_000.0
            turnover[-1] = 4.0
        frame = pd.DataFrame(
            {
                "date": dates,
                "open": close - 0.2,
                "high": close + 0.6,
                "low": close - 0.8,
                "close": close,
                "volume": volume,
                "amount": 100_000_000.0,
                "turnover": turnover,
            }
        )
        frame.attrs["source"] = "测试公开行情"
        frame.attrs["turnover_source"] = "测试换手率"
        return frame

    monkeypatch.setattr(app, "apply_product_theme", lambda: None)
    monkeypatch.setattr(app, "show_compact_page_header", lambda *args: None)
    monkeypatch.setattr(app, "show_product_footer", lambda: None)
    monkeypatch.setattr(
        app,
        "_browser_research_snapshot",
        lambda: {"watchlist": []},
    )
    monkeypatch.setattr(
        app,
        "load_a_share_directory",
        lambda: pd.DataFrame(
            {
                "code": ["600519", "300750"],
                "name": ["贵州茅台", "宁德时代"],
            }
        ),
    )
    monkeypatch.setattr(app, "load_a_share_history", fake_history)
    monkeypatch.setattr(
        app,
        "load_company_announcements",
        lambda code, *args, **kwargs: (
            pd.DataFrame(
                {
                    "code": ["600519"],
                    "name": ["贵州茅台"],
                    "title": ["贵州茅台2025年年度报告"],
                    "date": [date(2026, 7, 30)],
                    "url": [
                        "https://static.cninfo.com.cn/finalpage/"
                        "2026-07-30/1234567890.PDF"
                    ],
                    "category": ["财务报告"],
                    "attention": ["高"],
                }
            )
            if code == "600519"
            else pd.DataFrame(
                columns=[
                    "code",
                    "name",
                    "title",
                    "date",
                    "url",
                    "category",
                    "attention",
                ]
            )
        ),
    )
    monkeypatch.setattr(
        app.st,
        "text_area",
        lambda *args, **kwargs: "600519, 300750",
    )
    monkeypatch.setattr(
        app.st,
        "form_submit_button",
        lambda label, *args, **kwargs: label == "开始扫描自选股",
    )
    monkeypatch.setattr(
        app.st,
        "download_button",
        lambda label, **kwargs: downloads.append((label, kwargs)),
    )
    app.st.session_state.pop("market_radar_rows", None)
    app.st.session_state.pop("market_radar_failures", None)
    app.st.session_state.pop("market_radar_elapsed_seconds", None)

    app.render_market_radar_page()

    rows = app.st.session_state["market_radar_rows"]
    assert len(rows) == 2
    assert rows[0]["company"]["code"] == "600519"
    assert rows[0]["triggered_signals"] == [
        "明显放量",
        "普通换手率历史高位",
    ]
    assert rows[0]["research_priority"] == "P1｜立即核查"
    assert rows[0]["latest_disclosure"]["title"] == (
        "贵州茅台2025年年度报告"
    )
    assert app.st.session_state["market_radar_failures"] == []
    assert isinstance(
        app.st.session_state["market_radar_elapsed_seconds"],
        float,
    )
    assert downloads[0][0] == "下载自选股研究任务简报（HTML）"
    assert downloads[0][1]["mime"] == "text/html"
    assert b"WFZ" in downloads[0][1]["data"]


def test_market_radar_uses_three_bounded_company_workers(
    monkeypatch,
) -> None:
    """Keep known-code scans bounded without loading the full directory."""
    from src import app

    executor_workers = []
    submitted_codes = []

    class ImmediateFuture:
        def __init__(self, value):
            self.value = value

        def result(self):
            return self.value

    class RecordingExecutor:
        def __init__(self, *, max_workers, thread_name_prefix):
            executor_workers.append((max_workers, thread_name_prefix))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def submit(self, function, company, start_date, end_date):
            submitted_codes.append(company["code"])
            return ImmediateFuture(function(company, start_date, end_date))

    def fail_if_called():
        raise AssertionError("known radar codes should skip the live directory")

    monkeypatch.setattr(app, "ThreadPoolExecutor", RecordingExecutor)
    monkeypatch.setattr(app, "load_a_share_directory", fail_if_called)
    monkeypatch.setattr(
        app,
        "_scan_market_radar_company",
        lambda company, *args: {"company": company},
    )
    monkeypatch.setattr(app, "rank_research_queue", lambda rows: rows)

    rows, failures = app._scan_market_radar(
        ["600519", "300750", "000001", "002594", "000858"]
    )

    assert executor_workers == [(3, "wfz-radar")]
    assert submitted_codes == [
        "600519",
        "300750",
        "000001",
        "002594",
        "000858",
    ]
    assert [row["company"]["code"] for row in rows] == submitted_codes
    assert failures == []


def test_market_radar_loads_directory_for_an_unknown_valid_code(
    monkeypatch,
) -> None:
    """Preserve full-market coverage for codes outside the offline directory."""
    from src import app

    directory_calls = []

    def fake_directory():
        directory_calls.append(True)
        return pd.DataFrame(
            {
                "code": ["600000"],
                "name": ["浦发银行"],
            }
        )

    monkeypatch.setattr(app, "load_a_share_directory", fake_directory)
    monkeypatch.setattr(
        app,
        "_scan_market_radar_company",
        lambda company, *args: {"company": company},
    )
    monkeypatch.setattr(app, "rank_research_queue", lambda rows: rows)

    rows, failures = app._scan_market_radar(["600000"])

    assert directory_calls == [True]
    assert rows[0]["company"]["name"] == "浦发银行"
    assert failures == []


def test_market_radar_page_one_click_scans_device_local_watchlist(
    monkeypatch,
) -> None:
    """Use browser-local codes without replacing the manual input path."""
    from src import app

    scanned_codes = []
    input_defaults = []
    button_labels = []

    def fake_scan(codes: list[str]):
        scanned_codes.extend(codes)
        return [], []

    def fake_text_area(*args, **kwargs):
        input_defaults.append(kwargs["value"])
        return kwargs["value"]

    def fake_submit(label, *args, **kwargs):
        button_labels.append(label)
        return label.startswith("一键扫描我的本机自选股")

    monkeypatch.setattr(app, "apply_product_theme", lambda: None)
    monkeypatch.setattr(app, "show_compact_page_header", lambda *args: None)
    monkeypatch.setattr(app, "show_product_footer", lambda: None)
    monkeypatch.setattr(
        app,
        "_browser_research_snapshot",
        lambda: {
            "watchlist": [
                {"code": "600519", "name": "贵州茅台"},
                {"code": "300750", "name": "宁德时代"},
            ]
        },
    )
    monkeypatch.setattr(app.st, "text_area", fake_text_area)
    monkeypatch.setattr(app.st, "form_submit_button", fake_submit)
    monkeypatch.setattr(app, "_scan_market_radar", fake_scan)
    app.st.session_state.pop("market_radar_rows", None)
    app.st.session_state.pop("market_radar_failures", None)
    app.st.session_state.pop("market_radar_elapsed_seconds", None)

    app.render_market_radar_page()

    assert input_defaults == ["600519, 300750"]
    assert button_labels == [
        "一键扫描我的本机自选股（2家）",
        "开始扫描自选股",
    ]
    assert scanned_codes == ["600519", "300750"]
    assert app.st.session_state["market_radar_failures"] == []
    assert isinstance(
        app.st.session_state["market_radar_elapsed_seconds"],
        float,
    )


def test_limit_up_board_page_builds_daily_wall(monkeypatch) -> None:
    """Cover the new daily wall without calling the public provider."""
    from src import app

    pool_frame = pd.DataFrame(
        {
            "代码": ["600519", "300750"],
            "名称": ["贵州茅台", "宁德时代"],
            "涨跌幅": [10.0, 20.0],
            "最新价": [1321.0, 310.0],
            "成交额": [4_500_000_000, 6_000_000_000],
            "流通市值": [1_600_000_000_000, 1_200_000_000_000],
            "总市值": [1_700_000_000_000, 1_300_000_000_000],
            "换手率": [1.5, 4.5],
            "封板资金": [500_000_000, 300_000_000],
            "首次封板时间": [100501, 94530],
            "最后封板时间": [100501, 145000],
            "炸板次数": [0, 0],
            "涨停统计": ["2/2", "1/1"],
            "连板数": [2, 1],
            "所属行业": ["酿酒行业", "电池"],
        }
    )

    monkeypatch.setattr(app, "apply_product_theme", lambda: None)
    monkeypatch.setattr(app, "show_compact_page_header", lambda *args: None)
    monkeypatch.setattr(app, "show_product_footer", lambda: None)
    monkeypatch.setattr(app, "load_limit_up_pool", lambda *args: pool_frame)
    monkeypatch.setattr(
        app.st,
        "date_input",
        lambda *args, **kwargs: date(2026, 7, 30),
    )
    monkeypatch.setattr(
        app.st,
        "form_submit_button",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        app.st,
        "dataframe",
        lambda *args, **kwargs: None,
    )
    app.st.session_state.pop("limit_up_board_snapshot", None)

    app.render_limit_up_board_page()

    snapshot = app.st.session_state["limit_up_board_snapshot"]
    assert snapshot["total_count"] == 2
    assert snapshot["consecutive_board_count"] == 1
    assert snapshot["rows"][0]["code"] == "600519"
    assert snapshot["rows"][0]["first_limit_time"] == "10:05:01"
    assert snapshot["review"]["ladder"] == [
        {"boards": 2, "company_count": 1, "share": 0.5},
        {"boards": 1, "company_count": 1, "share": 0.5},
    ]
    assert snapshot["review"]["early_seal_count"] == 1
    assert snapshot["review"]["resealed_count"] == 0


def test_market_anomaly_page_builds_report_and_evidence_chain(
    monkeypatch,
) -> None:
    """Cover the dedicated Agent page without calling live data sources."""
    from src import app

    company = {
        "code": "600519",
        "name": "贵州茅台",
        "exchange": "SH",
        "exchange_name": "上海证券交易所",
        "canonical_code": "600519.SH",
    }
    dates = pd.date_range("2025-01-02", periods=300, freq="B")
    close = pd.Series([100 + index * 0.1 for index in range(len(dates))])
    market_frame = pd.DataFrame(
        {
            "date": dates,
            "open": close - 0.2,
            "high": close + 0.6,
            "low": close - 0.8,
            "close": close,
            "volume": [1_000_000] * 299 + [2_500_000],
            "amount": 100_000_000,
            "turnover": [1.0] * 299 + [4.0],
        }
    )
    market_frame.attrs["source"] = "测试公开行情"
    announcements = pd.DataFrame(
        {
            "date": [dates[-1].date()],
            "title": ["测试官方公告"],
            "url": ["https://static.cninfo.com.cn/test.pdf"],
            "category": ["其他公告"],
            "attention": ["低"],
        }
    )
    rendered_reports = []
    rendered_events = []

    monkeypatch.setattr(app, "apply_product_theme", lambda: None)
    monkeypatch.setattr(app, "show_compact_page_header", lambda *args: None)
    monkeypatch.setattr(app, "_selected_company", lambda: company)
    monkeypatch.setattr(app, "_show_company_banner", lambda selected: None)
    monkeypatch.setattr(
        app,
        "load_company_research_sources",
        lambda *args: (market_frame, announcements, None, None),
    )
    monkeypatch.setattr(
        app,
        "_show_market_anomaly_report",
        lambda report: rendered_reports.append(report),
    )
    monkeypatch.setattr(
        app,
        "_show_market_activity_evidence",
        lambda activity: None,
    )
    monkeypatch.setattr(
        app,
        "_show_anomaly_event_research",
        lambda events, selected, disclosures, **kwargs: rendered_events.extend(
            events
        ),
    )
    monkeypatch.setattr(app, "show_product_footer", lambda: None)

    app.render_market_anomaly_page()

    assert rendered_reports[0]["status"] == "compound_anomaly"
    assert rendered_reports[0]["triggered_signal_count"] == 2
    assert rendered_events[0]["event_type"] == (
        "明显放量 + 普通换手率高位"
    )


def test_historical_lens_page_renders_a_point_in_time_snapshot(
    monkeypatch,
) -> None:
    """Keep the new time-isolated page covered without calling live sources."""
    from src import app

    company = {
        "code": "600519",
        "name": "贵州茅台",
        "exchange": "SH",
        "exchange_name": "上海证券交易所",
        "canonical_code": "600519.SH",
    }
    dates = pd.date_range("2024-01-02", periods=700, freq="B")
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
            "date": [date.today()],
            "title": ["测试官方公告"],
            "url": ["https://static.cninfo.com.cn/test.pdf"],
            "category": ["其他公告"],
            "attention": ["低"],
        }
    )

    monkeypatch.setattr(app, "apply_product_theme", lambda: None)
    monkeypatch.setattr(app, "show_compact_page_header", lambda *args: None)
    monkeypatch.setattr(app, "_selected_company", lambda: company)
    monkeypatch.setattr(app, "_show_company_banner", lambda selected: None)
    monkeypatch.setattr(
        app,
        "load_a_share_history",
        lambda *args: market_frame,
    )
    monkeypatch.setattr(
        app,
        "load_company_announcements",
        lambda *args: announcements,
    )
    monkeypatch.setattr(
        app,
        "_build_kline_figure",
        lambda *args: object(),
    )
    monkeypatch.setattr(app.st, "plotly_chart", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        app,
        "select_latest_annual_report",
        lambda frame: None,
    )
    monkeypatch.setattr(app, "show_product_footer", lambda: None)

    app.render_historical_lens_page()


def test_financial_trend_page_renders_verified_flagship(
    monkeypatch,
) -> None:
    """Keep the standalone audited trend page independent of live sources."""
    from src import app

    company = {
        "code": "600519",
        "name": "贵州茅台",
        "exchange": "SH",
        "exchange_name": "上海证券交易所",
        "canonical_code": "600519.SH",
    }
    rendered_history = []

    monkeypatch.setattr(app, "apply_product_theme", lambda: None)
    monkeypatch.setattr(app, "show_compact_page_header", lambda *args: None)
    monkeypatch.setattr(app, "_selected_company", lambda: company)
    monkeypatch.setattr(app, "_show_company_banner", lambda selected: None)
    monkeypatch.setattr(
        app,
        "_show_verified_financial_history",
        lambda selected, cutoff: rendered_history.append(
            (selected, cutoff)
        ),
    )
    monkeypatch.setattr(app, "show_product_footer", lambda: None)

    app.render_financial_trend_page()

    assert rendered_history
    assert rendered_history[0][0]["code"] == "600519"


def test_financial_trend_page_renders_verified_catl(
    monkeypatch,
) -> None:
    """Keep the second audited company independent of live sources."""
    from src import app

    company = {
        "code": "300750",
        "name": "宁德时代",
        "exchange": "SZ",
        "exchange_name": "深圳证券交易所",
        "canonical_code": "300750.SZ",
    }
    rendered_history = []

    monkeypatch.setattr(app, "apply_product_theme", lambda: None)
    monkeypatch.setattr(app, "show_compact_page_header", lambda *args: None)
    monkeypatch.setattr(app, "_selected_company", lambda: company)
    monkeypatch.setattr(app, "_show_company_banner", lambda selected: None)
    monkeypatch.setattr(
        app,
        "_show_verified_financial_history",
        lambda selected, cutoff: rendered_history.append(
            (selected, cutoff)
        ),
    )
    monkeypatch.setattr(app, "show_product_footer", lambda: None)

    app.render_financial_trend_page()

    assert rendered_history
    assert rendered_history[0][0]["code"] == "300750"


def test_financial_trend_page_shows_catl_evidence_in_streamlit() -> None:
    """Render the real page controls, metrics, and official report links."""
    from streamlit.testing.v1 import AppTest

    script = """
from src import app

company = app.resolve_company("300750")[0]
app._selected_company = lambda: company
app._show_company_banner = lambda selected: None
app.render_financial_trend_page()
"""
    app_test = AppTest.from_string(script).run()
    visible_text = "\n".join(
        str(item.value)
        for group in (
            app_test.title,
            app_test.info,
            app_test.success,
            app_test.warning,
            app_test.caption,
            app_test.markdown,
        )
        for item in group
    )

    assert not app_test.exception
    assert "宁德时代" in visible_text
    assert "标准化接入检查通过" in visible_text
    assert "收入与利润方向不一致" in visible_text
    assert len(app_test.metric) == 12
    assert len(app_test.get("link_button")) == 3
    assert app_test.selectbox[0].value == "宁德时代｜300750.SZ"


def test_financial_trend_page_shows_byd_evidence_in_streamlit() -> None:
    """Prove the third catalogue company appears without page-code edits."""
    from streamlit.testing.v1 import AppTest

    script = """
from src import app

company = {
    "code": "002594",
    "name": "比亚迪",
    "exchange": "SZ",
    "exchange_name": "深圳证券交易所",
    "canonical_code": "002594.SZ",
}
app._selected_company = lambda: company
app._show_company_banner = lambda selected: None
app.render_financial_trend_page()
"""
    app_test = AppTest.from_string(script).run()
    visible_text = "\n".join(
        str(item.value)
        for group in (
            app_test.title,
            app_test.info,
            app_test.success,
            app_test.warning,
            app_test.caption,
            app_test.markdown,
        )
        for item in group
    )

    assert not app_test.exception
    assert "比亚迪" in visible_text
    assert "标准化接入检查通过" in visible_text
    assert "利润与经营现金方向不一致" in visible_text
    assert len(app_test.metric) == 12
    assert len(app_test.get("link_button")) == 3
    assert app_test.selectbox[0].value == "比亚迪｜002594.SZ"


def test_financial_trend_page_shows_midea_evidence_in_streamlit() -> None:
    """Prove Midea appears through the verified catalogue only."""
    from streamlit.testing.v1 import AppTest

    script = """
from src import app

company = {
    "code": "000333",
    "name": "美的集团",
    "exchange": "SZ",
    "exchange_name": "深圳证券交易所",
    "canonical_code": "000333.SZ",
}
app._selected_company = lambda: company
app._show_company_banner = lambda selected: None
app.render_financial_trend_page()
"""
    app_test = AppTest.from_string(script).run()
    visible_text = "\n".join(
        str(item.value)
        for group in (
            app_test.title,
            app_test.info,
            app_test.success,
            app_test.warning,
            app_test.caption,
            app_test.markdown,
        )
        for item in group
    )

    assert not app_test.exception
    assert "美的集团" in visible_text
    assert "标准化接入检查通过" in visible_text
    assert "利润与经营现金方向不一致" in visible_text
    assert len(app_test.metric) == 12
    assert len(app_test.get("link_button")) == 3
    assert app_test.selectbox[0].value == "美的集团｜000333.SZ"


def test_financial_anomaly_page_shows_verified_midea_bridge() -> None:
    """Render the controlled cash-flow explanation without live sources."""
    from streamlit.testing.v1 import AppTest

    script = """
from src import app

real_download_button = app.st.download_button

def capture_download(label, **kwargs):
    app.st.session_state["financial_anomaly_download_test"] = {
        "label": label,
        "file_name": kwargs["file_name"],
        "mime": kwargs["mime"],
        "byte_count": len(kwargs["data"]),
    }

try:
    app.st.download_button = capture_download
    app.render_financial_anomaly_explanation_page()
finally:
    app.st.download_button = real_download_button
"""
    app_test = AppTest.from_string(script).run()
    visible_text = "\n".join(
        str(item.value)
        for group in (
            app_test.title,
            app_test.info,
            app_test.success,
            app_test.warning,
            app_test.caption,
            app_test.subheader,
            app_test.markdown,
        )
        for item in group
    )

    assert not app_test.exception
    assert "财务异常解释 Agent" in visible_text
    assert "美的集团 2025 年" in visible_text
    assert "比亚迪 2024 年" in visible_text
    assert "当前收录 2 个受控案例" in visible_text
    assert "已证实" in visible_text
    assert "待进一步核查" in visible_text
    assert "年报第 233 页" in visible_text
    assert "不构成投资建议" in visible_text
    assert len(app_test.metric) == 3
    assert len(app_test.get("link_button")) == 1
    download = app_test.session_state["financial_anomaly_download_test"]
    assert download["label"] == "下载财务异常解释报告（HTML）"
    assert download["mime"] == "text/html"
    assert download["file_name"].endswith(
        "_financial_anomaly_explanation.html"
    )
    assert download["byte_count"] > 1_000
    assert app_test.selectbox[0].value == (
        "美的集团｜000333.SZ｜2025 年经营现金流背离"
    )
    assert list(app_test.selectbox[0].options) == [
        "美的集团｜000333.SZ｜2025 年经营现金流背离",
        "比亚迪｜002594.SZ｜2024 年经营现金流背离",
    ]


def test_financial_anomaly_page_switches_to_verified_byd_bridge() -> None:
    """Select the second case without requesting the live annual report."""
    from streamlit.testing.v1 import AppTest

    script = """
from src import app

app.st.session_state["financial_anomaly_case_selector"] = (
    "比亚迪｜002594.SZ｜2024 年经营现金流背离"
)
real_download_button = app.st.download_button

def capture_download(label, **kwargs):
    app.st.session_state["byd_anomaly_download_test"] = {
        "file_name": kwargs["file_name"],
        "byte_count": len(kwargs["data"]),
    }

try:
    app.st.download_button = capture_download
    app.render_financial_anomaly_explanation_page()
finally:
    app.st.download_button = real_download_button
"""
    app_test = AppTest.from_string(script).run()
    visible_text = "\n".join(
        str(item.value)
        for group in (
            app_test.title,
            app_test.info,
            app_test.success,
            app_test.warning,
            app_test.caption,
            app_test.subheader,
            app_test.markdown,
        )
        for item in group
    )

    assert not app_test.exception
    assert app_test.selectbox[0].value == (
        "比亚迪｜002594.SZ｜2024 年经营现金流背离"
    )
    assert "年报第 239 页" in visible_text
    assert "18 项调节数据与经营现金一致" in visible_text
    assert "存货增加对经营现金流的占用为什么扩大" in visible_text
    download = app_test.session_state["byd_anomaly_download_test"]
    assert download["file_name"] == (
        "002594_2024_financial_anomaly_explanation.html"
    )
    assert download["byte_count"] > 1_000


def test_financial_trend_page_shows_wuliangye_versions_in_streamlit() -> None:
    """Prove Wuliangye's four periods and five vintages render safely."""
    from streamlit.testing.v1 import AppTest

    script = """
from src import app

company = {
    "code": "000858",
    "name": "五粮液",
    "exchange": "SZ",
    "exchange_name": "深圳证券交易所",
    "canonical_code": "000858.SZ",
}
app._selected_company = lambda: company
app._show_company_banner = lambda selected: None
app.render_financial_trend_page()
"""
    app_test = AppTest.from_string(script).run()
    visible_text = "\n".join(
        str(item.value)
        for group in (
            app_test.title,
            app_test.info,
            app_test.success,
            app_test.warning,
            app_test.caption,
            app_test.markdown,
        )
        for item in group
    )

    assert not app_test.exception
    assert "五粮液" in visible_text
    assert "标准化接入检查通过" in visible_text
    assert "追溯调整版本 1 个" in visible_text
    assert len(app_test.metric) == 12
    assert len(app_test.get("link_button")) == 4
    assert app_test.selectbox[0].value == "五粮液｜000858.SZ"


def test_cross_company_comparison_page_shows_common_year_evidence() -> None:
    """Render the comparison page with all six audited companies."""
    from streamlit.testing.v1 import AppTest

    script = """
from src import app

app.render_cross_company_comparison_page()
"""
    app_test = AppTest.from_string(script).run()
    visible_text = "\n".join(
        str(item.value)
        for group in (
            app_test.title,
            app_test.info,
            app_test.success,
            app_test.warning,
            app_test.caption,
            app_test.subheader,
            app_test.markdown,
        )
        for item in group
    )

    assert not app_test.exception
    assert "跨公司横向比较工作台" in visible_text
    assert "跨行业比较（4个研究组）" in visible_text
    assert "行业证据与同行组状态" in visible_text
    assert "已建立同行组候选覆盖：白酒制造" in visible_text
    assert "共同年度检查通过" in visible_text
    assert "不含估值、预测或买卖建议" in visible_text
    assert app_test.multiselect[0].value == [
        "贵州茅台｜600519.SH",
        "五粮液｜000858.SZ",
        "泸州老窖｜000568.SZ",
        "宁德时代｜300750.SZ",
        "比亚迪｜002594.SZ",
        "美的集团｜000333.SZ",
    ]
    assert app_test.selectbox[0].value == 2024
    assert len(app_test.metric) == 4
    assert len(app_test.get("link_button")) == 6


def test_cross_company_page_can_select_the_baijiu_peer_candidate() -> None:
    """Switch the page from the default cross-industry view to baijiu."""
    from streamlit.testing.v1 import AppTest

    script = """
from src import app

app.render_cross_company_comparison_page()
"""
    app_test = AppTest.from_string(script).run()
    app_test.multiselect[0].set_value(
        [
            "贵州茅台｜600519.SH",
            "五粮液｜000858.SZ",
            "泸州老窖｜000568.SZ",
        ]
    ).run()
    visible_text = "\n".join(
        str(item.value)
        for group in (
            app_test.subheader,
            app_test.success,
            app_test.warning,
            app_test.caption,
            app_test.markdown,
        )
        for item in group
    )

    assert not app_test.exception
    assert "同行组候选｜白酒制造" in visible_text
    assert "白酒经营质量透视｜2025" in visible_text
    assert "2023—2025经营质量趋势" in visible_text
    assert "不生成综合得分" in visible_text
    assert app_test.selectbox[0].value == 2025
    assert len(app_test.get("link_button")) == 3
