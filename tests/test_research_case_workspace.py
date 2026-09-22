from __future__ import annotations

from copy import deepcopy
from datetime import date
from types import SimpleNamespace

import pytest

from src.china_stock import build_company_identity
from src.research_case import (
    empty_research_case_store,
    new_research_case,
    reduce_research_case_store,
)


NOW = "2026-08-30T12:00:00+00:00"


def _company() -> dict[str, str]:
    return build_company_identity("600519", "贵州茅台")


def _case() -> dict[str, object]:
    return new_research_case(
        "case-workspace-600519",
        _company(),
        mode="current",
        as_of_date=None,
        effective_market_date="2026-08-29",
        created_at=NOW,
    )


def _store_with_case() -> dict[str, object]:
    store = empty_research_case_store()
    return reduce_research_case_store(
        store,
        {
            "command_id": "workspace-create-1",
            "base_store_revision": store["store_revision"],
            "action": "create",
            "emitted_at": NOW,
            "case_id": "case-workspace-600519",
            "company": _company(),
            "mode": "current",
            "as_of_date": None,
            "effective_market_date": "2026-08-29",
        },
    )


def _rendered_text(app_test: object) -> str:
    """Collect the user-visible text needed by workspace contract tests."""
    values: list[str] = []
    for collection_name in (
        "markdown",
        "info",
        "warning",
        "error",
        "caption",
        "text",
    ):
        for element in getattr(app_test, collection_name, []):
            value = getattr(element, "value", None)
            if isinstance(value, str):
                values.append(value)
    return "\n".join(values)


def test_ensure_company_research_case_creates_then_reuses_current_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeated research of one company must not silently fork its case."""
    from src import app

    monkeypatch.setattr(app, "_utc_today", lambda: date(2026, 8, 30))
    empty = empty_research_case_store()

    created_store, created_case = app._ensure_company_research_case(
        empty,
        _company(),
    )
    reused_store, reused_case = app._ensure_company_research_case(
        created_store,
        _company(),
    )

    assert len(created_store["cases"]) == 1
    assert reused_case["case_id"] == created_case["case_id"]
    assert reused_store["active_case_id"] == created_case["case_id"]
    assert reused_store["store_revision"] == created_store["store_revision"]
    assert reused_store["cases"] == created_store["cases"]


def test_reused_current_case_rolls_forward_before_new_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A current case cannot keep an old cut-off while accepting new data."""
    from src import app

    monkeypatch.setattr(app, "_utc_today", lambda: date(2026, 8, 30))
    store = _store_with_case()

    updated, case = app._ensure_company_research_case(store, _company())

    assert case["scope"]["effective_market_date"] == "2026-08-30"
    assert case["revision"] == 1
    assert updated["store_revision"] == store["store_revision"] + 1
    assert "推进至2026-08-30" in case["audit_log"][-1]["message"]


def test_stage_research_case_store_keeps_explicit_base_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pending write must retain the revision it was derived from."""
    from src import app

    session_state: dict[str, object] = {}
    monkeypatch.setattr(app, "st", SimpleNamespace(session_state=session_state))
    store = _store_with_case()

    app._stage_research_case_store(store, base_store_revision=0)

    assert session_state[app.RESEARCH_CASE_STORE_SESSION_KEY] == store
    assert session_state[app.RESEARCH_CASE_PENDING_SESSION_KEY] == store
    assert session_state[app.RESEARCH_CASE_PENDING_BASE_KEY] == 0
    assert store["store_revision"] == 1


def test_historical_lock_updates_same_current_company_case_without_future_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Historical Lens is evidence inside one company case, not a case per date."""
    from src import app

    session_state: dict[str, object] = {
        app.RESEARCH_CASE_STORE_SESSION_KEY: empty_research_case_store(),
        app.RESEARCH_CASE_STORAGE_STATUS_KEY: "available",
        app.RESEARCH_CASE_HYDRATED_KEY: True,
    }
    monkeypatch.setattr(app, "st", SimpleNamespace(session_state=session_state))
    snapshot = {
        "requested_date": date(2025, 4, 10),
        "effective_market_date": date(2025, 4, 10),
        "latest_close": 1520.5,
        "volume": 1_234_567.0,
        "turnover": 0.0075,
        "return_20d": 0.03,
        "return_60d": -0.02,
        "return_250d": 0.12,
        "annualised_volatility": 0.24,
        "max_drawdown": -0.16,
        "observations": 251,
        "source": "公开行情适配器",
        "adjustment": "不复权",
        "later_outcomes": [{"return_since_base": 9.99}],
    }
    evidence_result = {
        "as_of_date": date(2025, 4, 10),
        "accepted": [
            {
                "source_id": "official-1",
                "source_type": "年度报告",
                "title": "当时已公开的官方公告",
                "published_date": date(2025, 4, 9),
                "period_end": None,
                "source_url": "https://static.cninfo.com.cn/official-1.pdf",
                "page_number": 18,
                "evidence_grade": "A",
                "verification_status": "verified",
            }
        ],
        "excluded": [],
        "input_count": 1,
        "accepted_count": 1,
        "excluded_count": 0,
    }

    app._write_historical_snapshot_to_research_case(
        _company(),
        snapshot,
        evidence_result,
    )

    pending = session_state[app.RESEARCH_CASE_PENDING_SESSION_KEY]
    assert len(pending["cases"]) == 1
    case = pending["cases"][pending["active_case_id"]]
    assert case["scope"]["mode"] == "current"
    assert case["questions"]["point_in_time"]["status"] == "answered"
    payload = case["artifacts"][0]["payload"]
    assert payload["cutoff_date"] == "2025-04-10"
    assert "later_outcomes" not in payload


def test_historical_writeback_retry_does_not_stage_a_duplicate_browser_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retrying one locked snapshot must leave revision and storage untouched."""
    from src import app

    session_state: dict[str, object] = {
        app.RESEARCH_CASE_STORE_SESSION_KEY: empty_research_case_store(),
        app.RESEARCH_CASE_STORAGE_STATUS_KEY: "available",
        app.RESEARCH_CASE_HYDRATED_KEY: True,
    }
    monkeypatch.setattr(app, "st", SimpleNamespace(session_state=session_state))
    monkeypatch.setattr(app, "_utc_today", lambda: date(2026, 8, 30))
    snapshot = {
        "requested_date": date(2025, 4, 10),
        "effective_market_date": date(2025, 4, 10),
        "latest_close": 1520.5,
        "volume": 1_234_567.0,
        "turnover": 0.0075,
        "return_20d": 0.03,
        "return_60d": -0.02,
        "return_250d": 0.12,
        "annualised_volatility": 0.24,
        "max_drawdown": -0.16,
        "observations": 251,
        "source": "公开行情适配器",
        "adjustment": "不复权",
    }
    evidence_result = {
        "as_of_date": date(2025, 4, 10),
        "accepted": [
            {
                "source_id": "official-1",
                "source_type": "年度报告",
                "title": "当时已公开的官方公告",
                "published_date": date(2025, 4, 9),
                "period_end": None,
                "source_url": "https://static.cninfo.com.cn/official-1.pdf",
                "page_number": 18,
                "evidence_grade": "A",
                "verification_status": "verified",
            }
        ],
        "excluded": [],
        "input_count": 1,
        "accepted_count": 1,
        "excluded_count": 0,
    }

    app._write_historical_snapshot_to_research_case(
        _company(), snapshot, evidence_result
    )
    first_store = deepcopy(
        session_state[app.RESEARCH_CASE_STORE_SESSION_KEY]
    )
    first_case = first_store["cases"][first_store["active_case_id"]]
    first_audit_count = len(first_case["audit_log"])
    session_state.pop(app.RESEARCH_CASE_PENDING_SESSION_KEY)
    session_state.pop(app.RESEARCH_CASE_PENDING_BASE_KEY)

    app._write_historical_snapshot_to_research_case(
        _company(), snapshot, evidence_result
    )

    second_store = session_state[app.RESEARCH_CASE_STORE_SESSION_KEY]
    second_case = second_store["cases"][second_store["active_case_id"]]
    assert second_store == first_store
    assert len(second_case["audit_log"]) == first_audit_count
    assert app.RESEARCH_CASE_PENDING_SESSION_KEY not in session_state
    assert "没有重复增加" in session_state[
        "_wfz_historical_case_writeback_notice"
    ]


def test_empty_workspace_does_not_claim_that_no_contradictions_exist() -> None:
    """No case/no evidence is uncertainty, never proof of consistency."""
    from streamlit.testing.v1 import AppTest

    script = '''
from src import app

originals = {
    "apply_product_theme": app.apply_product_theme,
    "_sync_research_case_store": app._sync_research_case_store,
    "show_compact_page_header": app.show_compact_page_header,
    "_render_research_case_storage_notice": app._render_research_case_storage_notice,
    "_selected_company": app._selected_company,
    "_render_company_search": app._render_company_search,
    "show_product_footer": app.show_product_footer,
}
try:
    app.apply_product_theme = lambda: None
    app._sync_research_case_store = lambda: None
    app.show_compact_page_header = lambda *args, **kwargs: None
    app._render_research_case_storage_notice = lambda: None
    app._selected_company = lambda: None
    app._render_company_search = lambda **kwargs: None
    app.show_product_footer = lambda: None
    app.render_research_workspace_page()
finally:
    for name, value in originals.items():
        setattr(app, name, value)
'''
    app_test = AppTest.from_string(script).run(timeout=10)

    assert not app_test.exception
    page_text = _rendered_text(app_test)
    assert "尚未建立研究案件" in page_text
    assert "无矛盾" not in page_text
    assert "没有矛盾" not in page_text
    assert "证据彼此一致" not in page_text


def test_active_case_displays_exactly_the_five_core_research_questions() -> None:
    """The case front door must lead with the five user-requested answers."""
    from streamlit.testing.v1 import AppTest

    script = '''
from src.app import _render_research_case_brief
from src.research_case import new_research_case

case = new_research_case(
    "case-workspace-600519",
    {
        "code": "600519",
        "canonical_code": "600519.SH",
        "name": "贵州茅台",
        "exchange": "SH",
        "exchange_name": "上海证券交易所",
    },
    mode="current",
    as_of_date=None,
    effective_market_date="2026-08-29",
    created_at="2026-08-30T12:00:00+00:00",
)
_render_research_case_brief(case)
'''
    app_test = AppTest.from_string(script).run(timeout=10)

    assert not app_test.exception
    page_text = _rendered_text(app_test)
    expected = (
        "01｜当前最值得核验的问题是什么",
        "02｜已经有什么证据",
        "03｜哪些证据互相矛盾",
        "04｜还有什么未知",
        "05｜下一步应该验证什么",
    )
    for heading in expected:
        assert page_text.count(heading) == 1
    assert "这里为空不等于证据彼此一致" in page_text


def test_export_gaps_distinguish_analysis_from_real_evidence_and_blocked_lanes() -> None:
    """UI must explain why an analysis-only case is not a formal workpaper."""
    from src import app

    case = _case()
    case["artifacts"] = [
        {
            "artifact_id": "artifact-analysis-only",
            "module": "annual_report",
            "title": "AI分析输出",
            "generated_at": NOW,
            "payload": {"summary": "仅有分析，没有来源证据。"},
            "review_status": "not_required",
        }
    ]
    case["case_brief"]["primary_question"] = "现金质量是否可靠？"
    case["case_brief"]["evidence"] = {
        "summary": "模型生成了一段摘要。",
        "artifact_ids": ["artifact-analysis-only"],
        "evidence_ids": [],
    }
    case["case_brief"]["next_action"] = {
        "module": "annual_report",
        "action": "核对原文",
        "reason": "分析输出不能替代来源证据。",
    }
    for question in case["questions"].values():
        question.update(
            {
                "status": "blocked",
                "summary": "仍缺来源证据。",
                "next_action": "补充并核验官方来源。",
                "artifact_ids": ["artifact-analysis-only"],
                "evidence_ids": [],
            }
        )
    case["questions"]["point_in_time"]["next_action"] = ""

    gaps = app._research_case_export_gaps(case)

    assert any("可追溯来源的证据引用" in gap for gap in gaps)
    assert any("五个专题不能全部阻塞" in gap for gap in gaps)
    assert any("阻塞专题尚未说明证据缺口与下一步" in gap for gap in gaps)
    assert not any("尚未形成带引用的证据摘要" in gap for gap in gaps)


def test_unavailable_local_storage_keeps_in_memory_pending_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persistence failure must degrade explicitly without dropping work."""
    from src import app

    stored = _store_with_case()
    pending = deepcopy(stored)
    session_state: dict[str, object] = {
        app.RESEARCH_CASE_STORE_SESSION_KEY: stored,
        app.RESEARCH_CASE_PENDING_SESSION_KEY: pending,
        app.RESEARCH_CASE_PENDING_BASE_KEY: 0,
        app.RESEARCH_CASE_STORAGE_STATUS_KEY: "available",
        app.RESEARCH_CASE_HYDRATED_KEY: True,
        "_wfz_research_case_writer_id": "a" * 32,
    }
    monkeypatch.setattr(app, "st", SimpleNamespace(session_state=session_state))
    monkeypatch.setattr(
        app,
        "_RESEARCH_CASE_STORAGE",
        lambda **kwargs: {
            "snapshot": kwargs["default"]["snapshot"],
            "storage_status": "unavailable",
        },
    )

    app._sync_research_case_store()

    assert session_state[app.RESEARCH_CASE_STORAGE_STATUS_KEY] == "unavailable"
    assert session_state[app.RESEARCH_CASE_STORE_SESSION_KEY] == pending
    assert session_state[app.RESEARCH_CASE_STORE_SESSION_KEY]["active_case_id"] == (
        "case-workspace-600519"
    )
    assert app.RESEARCH_CASE_PENDING_SESSION_KEY not in session_state
    assert app.RESEARCH_CASE_PENDING_BASE_KEY not in session_state


def test_available_but_deep_invalid_browser_store_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A shallow-valid browser value must not overwrite or unlock case data."""
    from src import app

    current = _store_with_case()
    malformed = {
        "schema_version": "1.0",
        "store_revision": 2,
        "active_case_id": "case-bad",
        "cases": {"case-bad": {"case_id": "case-bad"}},
    }
    session_state: dict[str, object] = {
        app.RESEARCH_CASE_STORE_SESSION_KEY: current,
        app.RESEARCH_CASE_STORAGE_STATUS_KEY: "pending",
        app.RESEARCH_CASE_HYDRATED_KEY: False,
        "_wfz_research_case_writer_id": "a" * 32,
    }
    monkeypatch.setattr(app, "st", SimpleNamespace(session_state=session_state))
    monkeypatch.setattr(
        app,
        "_RESEARCH_CASE_STORAGE",
        lambda **_kwargs: {
            "snapshot": malformed,
            "storage_status": "available",
        },
    )

    app._sync_research_case_store()

    assert session_state[app.RESEARCH_CASE_STORAGE_STATUS_KEY] == "invalid"
    assert session_state[app.RESEARCH_CASE_HYDRATED_KEY] is True
    assert session_state[app.RESEARCH_CASE_STORE_SESSION_KEY] == current
    assert app._research_case_write_ready() is False
