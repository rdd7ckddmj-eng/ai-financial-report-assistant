from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from src.china_stock import build_company_identity
from src.financial_snapshot_review import (
    CORE_METRIC_KEYS,
    FinancialSnapshotReviewError,
    build_exportable_review_workpaper,
    build_financial_snapshot_review,
    confirm_snapshot_metric,
    correct_snapshot_metric,
    reject_snapshot_metric,
)
from src.research_case import empty_research_case_store, reduce_research_case_store


NOW = "2026-08-30T12:00:00+00:00"


def _company() -> dict[str, str]:
    return build_company_identity("600519", "贵州茅台")


def _store_with_current_case() -> dict[str, object]:
    store = empty_research_case_store()
    return reduce_research_case_store(
        store,
        {
            "command_id": "financial-review-case-create",
            "base_store_revision": store["store_revision"],
            "action": "create",
            "emitted_at": NOW,
            "case_id": "case-financial-review-600519",
            "company": _company(),
            "mode": "current",
            "as_of_date": None,
            "effective_market_date": "2026-08-29",
        },
    )


def _snapshot() -> dict[str, object]:
    values = {
        "revenue": 10_000_000.0,
        "net_profit": 1_000_000.0,
        "operating_cash_flow": 1_250_000.0,
        "total_assets": 20_000_000.0,
        "total_liabilities": 8_000_000.0,
    }
    labels = {
        "revenue": "营业收入",
        "net_profit": "净利润（优先归母口径）",
        "operating_cash_flow": "经营活动现金流量净额",
        "total_assets": "资产总额",
        "total_liabilities": "负债总额",
    }
    statements = {
        "revenue": "利润表",
        "net_profit": "利润表",
        "operating_cash_flow": "现金流量表",
        "total_assets": "资产负债表",
        "total_liabilities": "资产负债表",
    }
    metrics: list[dict[str, object]] = []
    for page, key in enumerate(CORE_METRIC_KEYS, start=91):
        value = values[key]
        pages = {"start": page, "end": page}
        metrics.append(
            {
                "key": key,
                "label": labels[key],
                "current_yuan": value,
                "statement": statements[key],
                "pages": pages,
                "source": {
                    "raw_current_value": value / 10_000,
                    "raw_previous_value": value * 0.9 / 10_000,
                    "original_unit": "万元",
                    "accounting_basis": "合并口径",
                    "comparison_basis": "本期与年报比较栏原值",
                    "statement": statements[key],
                    "pages": pages,
                    "excerpt": f"{labels[key]} 本期 {value / 10_000:.0f} 万元",
                    "excerpt_status": "captured",
                },
            }
        )
    return {
        "schema_version": "1.1",
        "company": _company(),
        "report": {
            "report_year": 2025,
            "published_date": "2026-04-20",
            "title": "贵州茅台2025年年度报告",
            "source_url": (
                "https://static.cninfo.com.cn/finalpage/2026-04-20/"
                "1219999999.PDF"
            ),
        },
        "source_fingerprint_sha256": "a" * 64,
        "metrics": metrics,
    }


def _review(*, rejected_key: str | None = None) -> dict[str, object]:
    review = build_financial_snapshot_review(
        _snapshot(),
        review_id="review-app-writeback-1",
        created_at="2026-08-30T12:01:00+00:00",
    )
    for minute, key in enumerate(CORE_METRIC_KEYS, start=2):
        if key == rejected_key:
            review = reject_snapshot_metric(
                review,
                key,
                "原文口径无法可靠核验，该自动提取值不得使用。",
                decided_at=f"2026-08-30T12:0{minute}:00+00:00",
            )
        else:
            review = confirm_snapshot_metric(
                review,
                key,
                decided_at=f"2026-08-30T12:0{minute}:00+00:00",
            )
    return review


def _workpaper(*, rejected_key: str | None = None) -> dict[str, object]:
    return build_exportable_review_workpaper(
        _review(rejected_key=rejected_key),
        exported_at="2026-08-30T12:10:00+00:00",
    )


def _ready_session(app: object, store: dict[str, object]) -> dict[str, object]:
    return {
        app.RESEARCH_CASE_STORE_SESSION_KEY: store,
        app.RESEARCH_CASE_STORAGE_STATUS_KEY: "available",
        app.RESEARCH_CASE_HYDRATED_KEY: True,
    }


def test_review_corrected_to_loss_can_still_be_written_to_case(monkeypatch):
    from src import app
    review = correct_snapshot_metric(_review(), 'net_profit', -1_000_000,
        '核对原文后更正为亏损。', decided_at='2026-08-30T12:09:00+00:00')
    workpaper = build_exportable_review_workpaper(review, exported_at='2026-08-30T12:10:00+00:00')
    assert workpaper['ratios']['operating_cash_conversion'] is None
    session = _ready_session(app, _store_with_current_case())
    monkeypatch.setattr(app, 'st', SimpleNamespace(session_state=session))
    app._write_financial_review_to_research_case(_company(), workpaper)
    pending = session[app.RESEARCH_CASE_PENDING_SESSION_KEY]
    case = pending['cases'][pending['active_case_id']]
    assert len(case['evidence']) == 5


def test_completed_review_writes_into_same_current_company_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src import app

    original = _store_with_current_case()
    original_case_id = original["active_case_id"]
    session_state = _ready_session(app, original)
    monkeypatch.setattr(app, "st", SimpleNamespace(session_state=session_state))

    app._write_financial_review_to_research_case(_company(), _workpaper())

    pending = session_state[app.RESEARCH_CASE_PENDING_SESSION_KEY]
    assert len(pending["cases"]) == 1
    assert pending["active_case_id"] == original_case_id
    case = pending["cases"][original_case_id]
    assert case["questions"]["financial_quality"]["status"] == "answered"
    assert len(case["evidence"]) == 5
    assert [artifact["module"] for artifact in case["artifacts"]] == [
        "financial_snapshot"
    ]
    assert "同一份研究案件" in session_state[
        "_wfz_financial_case_writeback_notice"
    ]


def test_partial_review_has_no_exportable_workpaper_and_helper_does_not_stage_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src import app

    partial_review = build_financial_snapshot_review(
        _snapshot(),
        review_id="review-app-partial",
        created_at="2026-08-30T12:01:00+00:00",
    )
    with pytest.raises(FinancialSnapshotReviewError, match="尚未全部完成"):
        build_exportable_review_workpaper(partial_review)

    original = _store_with_current_case()
    original_copy = deepcopy(original)
    session_state = _ready_session(app, original)
    monkeypatch.setattr(app, "st", SimpleNamespace(session_state=session_state))

    # Defence in depth: even a caller bypassing the page gate cannot stage a
    # pending review because the write helper accepts only a gated workpaper.
    app._write_financial_review_to_research_case(_company(), partial_review)

    assert session_state[app.RESEARCH_CASE_STORE_SESSION_KEY] == original_copy
    assert app.RESEARCH_CASE_PENDING_SESSION_KEY not in session_state
    assert "_wfz_financial_case_writeback_error" in session_state
    case = original_copy["cases"][original_copy["active_case_id"]]
    assert case["evidence"] == []
    assert case["artifacts"] == []


def test_rejected_metric_is_unknown_and_never_case_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src import app

    session_state = _ready_session(app, _store_with_current_case())
    monkeypatch.setattr(app, "st", SimpleNamespace(session_state=session_state))

    app._write_financial_review_to_research_case(
        _company(),
        _workpaper(rejected_key="net_profit"),
    )

    pending = session_state[app.RESEARCH_CASE_PENDING_SESSION_KEY]
    case = pending["cases"][pending["active_case_id"]]
    assert len(case["evidence"]) == 4
    assert all("净利润" not in item["title"] for item in case["evidence"])
    assert any(
        "净利润" in item["summary"] and "不得用于" in item["summary"]
        for item in case["case_brief"]["unknowns"]
    )
    artifact = next(
        item for item in case["artifacts"] if item["module"] == "financial_snapshot"
    )
    rejected = next(
        item
        for item in artifact["payload"]["metrics"]
        if item["key"] == "net_profit"
    )
    assert rejected["decision"] == "rejected"
    assert "effective_value_yuan" not in rejected
    assert "original_value_yuan" not in rejected


def test_same_review_detector_blocks_a_second_ui_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src import app

    workpaper = _workpaper()
    session_state = _ready_session(app, _store_with_current_case())
    monkeypatch.setattr(app, "st", SimpleNamespace(session_state=session_state))
    app._write_financial_review_to_research_case(_company(), workpaper)
    first_pending = deepcopy(session_state[app.RESEARCH_CASE_PENDING_SESSION_KEY])

    assert app._financial_review_is_in_research_case(
        _company(), workpaper["review_id"]
    )
    # This is the same guard used by render_financial_snapshot_page before it
    # exposes the write button.  A repeated click/rerun therefore does not call
    # the mutation helper or create a second artifact.
    if not app._financial_review_is_in_research_case(
        _company(), workpaper["review_id"]
    ):
        app._write_financial_review_to_research_case(_company(), workpaper)

    assert session_state[app.RESEARCH_CASE_PENDING_SESSION_KEY] == first_pending
    case = first_pending["cases"][first_pending["active_case_id"]]
    assert len(case["artifacts"]) == 1
    assert not app._financial_review_is_in_research_case(
        _company(), "review-app-writeback-other"
    )
