from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.audited_company_onboarding import build_candidate_report_result
from src.financial_snapshot_review import (
    CORE_METRIC_KEYS,
    FinancialSnapshotReviewError,
    build_exportable_review_workpaper,
    build_financial_snapshot_review,
    confirm_snapshot_metric,
    correct_snapshot_metric,
    reject_snapshot_metric,
    serialise_review_workpaper,
)
from src.on_demand_financial_snapshot import (
    build_on_demand_financial_snapshot,
)


def _company() -> dict[str, str]:
    return {
        "code": "600000",
        "name": "测试公司",
        "exchange": "SH",
        "exchange_name": "上海证券交易所",
        "canonical_code": "600000.SH",
    }


def _legacy_candidate() -> dict[str, object]:
    return {
        "report_year": 2025,
        "published_date": "2026-04-20",
        "title": "测试公司2025年年度报告",
        "source_url": "https://static.cninfo.com.cn/example.pdf",
        "evidence_fingerprint_sha256": "a" * 64,
        "page_count": 200,
        "status": "ready_for_human_review",
        "statement_checks": {
            "income_statement_reconciled": True,
            "balance_sheet_reconciled": True,
            "cash_flow_statement_reconciled": True,
        },
        "unit_check": {
            "passed": True,
            "units": ["万元", "万元", "万元"],
            "note": "三张报表金额单位一致。",
        },
        "statement_pages": {
            "income_statement": {"start": 100, "end": 101},
            "balance_sheet": {"start": 98, "end": 99},
            "cash_flow_statement": {"start": 102, "end": 103},
        },
        "values": {
            "current_revenue": 1000.0,
            "previous_revenue": 900.0,
            "current_net_profit": 100.0,
            "previous_net_profit": 80.0,
            "current_operating_cash_flow": 125.0,
            "previous_operating_cash_flow": 70.0,
            "current_total_assets": 2000.0,
            "previous_total_assets": 1800.0,
            "current_total_liabilities": 800.0,
            "previous_total_liabilities": 750.0,
        },
    }


def _snapshot() -> dict[str, object]:
    return build_on_demand_financial_snapshot(
        _company(),
        _legacy_candidate(),  # type: ignore[arg-type]
        generated_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
    )


def test_candidate_retains_compact_source_evidence_for_each_core_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    income = {
        "current_revenue": 1000.0,
        "previous_revenue": 900.0,
        "current_net_profit": 100.0,
        "previous_net_profit": 80.0,
        "unit": "人民币万元",
        "page_number": 101,
        "end_page_number": 101,
    }
    balance = {
        "current_total_assets": 2000.0,
        "previous_total_assets": 1800.0,
        "current_total_liabilities": 800.0,
        "previous_total_liabilities": 750.0,
        "unit": "人民币万元",
        "page_number": 99,
        "end_page_number": 99,
    }
    cash_flow = {
        "current_operating_cash_flow": 125.0,
        "previous_operating_cash_flow": 70.0,
        "unit": "人民币万元",
        "page_number": 103,
        "end_page_number": 103,
    }
    monkeypatch.setattr(
        "src.audited_company_onboarding.find_income_statement_figures",
        lambda pages: income,
    )
    monkeypatch.setattr(
        "src.audited_company_onboarding.find_balance_sheet_figures",
        lambda pages: balance,
    )
    monkeypatch.setattr(
        "src.audited_company_onboarding.find_cash_flow_figures",
        lambda pages: cash_flow,
    )

    result = build_candidate_report_result(
        _company(),
        {
            "report_year": 2025,
            "published_date": "2026-04-20",
            "title": "测试公司2025年年度报告",
            "url": "https://static.cninfo.com.cn/example.pdf",
        },
        b"%PDF-compact-source-only",
        [
            {
                "page_number": 99,
                "text": "合并资产负债表\n单位：人民币万元\n资产总计\n2000\n1800\n负债合计\n800\n750",
            },
            {
                "page_number": 101,
                "text": "合并利润表\n单位：人民币万元\n营业收入\n1000\n900\n归属于母公司股东的净利润\n100\n80",
            },
            {
                "page_number": 103,
                "text": "合并现金流量表\n单位：人民币万元\n经营活动产生的现金流量净额\n125\n70",
            },
        ],
    )

    assert set(result["metric_evidence"]) == set(CORE_METRIC_KEYS)
    revenue = result["metric_evidence"]["revenue"]
    assert revenue["raw_current_value"] == 1000.0
    assert revenue["original_unit"] == "人民币万元"
    assert revenue["accounting_basis"] == "合并口径"
    assert revenue["pages"] == {"start": 101, "end": 101}
    assert "营业收入" in revenue["excerpt"]
    assert revenue["excerpt_status"] == "captured"
    assert all(
        len(str(item["excerpt"])) <= 480
        for item in result["metric_evidence"].values()
    )
    assert b"%PDF" not in repr(result).encode("utf-8")


def test_legacy_candidate_missing_excerpt_is_explicit_not_invented() -> None:
    snapshot = _snapshot()

    revenue = snapshot["metrics"][0]
    assert revenue["source"]["raw_current_value"] == 1000.0
    assert revenue["source"]["original_unit"] == "万元"
    assert revenue["source"]["pages"] == {"start": 100, "end": 101}
    assert revenue["source"]["excerpt"] == ""
    assert revenue["source"]["excerpt_status"] == "unavailable_legacy"
    assert revenue["source"]["accounting_basis"] == "报表口径待人工确认"


def test_extraction_starts_pending_and_cannot_be_exported_automatically() -> None:
    review = build_financial_snapshot_review(
        _snapshot(),
        review_id="review-1",
        created_at="2026-08-30T12:00:00+00:00",
    )

    assert review["status"] == "pending_human_review"
    assert {metric["decision"] for metric in review["metrics"]} == {"pending"}
    with pytest.raises(FinancialSnapshotReviewError, match="尚未全部"):
        build_exportable_review_workpaper(review)


def test_correction_and_rejection_require_reasons_and_preserve_original() -> None:
    review = build_financial_snapshot_review(_snapshot())

    with pytest.raises(FinancialSnapshotReviewError, match="必须填写理由"):
        correct_snapshot_metric(review, "revenue", 11_000_000, "")
    with pytest.raises(FinancialSnapshotReviewError, match="必须填写理由"):
        reject_snapshot_metric(review, "revenue", "")

    corrected = correct_snapshot_metric(
        review,
        "revenue",
        11_000_000,
        "原页面数字识别遗漏一位，已按第100页人工更正。",
        decided_at="2026-08-30T12:10:00+00:00",
    )
    metric = corrected["metrics"][0]
    assert metric["original_value_yuan"] == 10_000_000
    assert metric["corrected_value_yuan"] == 11_000_000
    assert metric["decision"] == "corrected"
    assert metric["source"] == review["metrics"][0]["source"]
    assert review["metrics"][0]["decision"] == "pending"


def test_all_five_explicit_decisions_open_a_compact_export_gate() -> None:
    review = build_financial_snapshot_review(_snapshot(), review_id="review-2")
    review = correct_snapshot_metric(
        review,
        "revenue",
        11_000_000,
        "人工对照第100页后更正。",
    )
    for metric_key in CORE_METRIC_KEYS[1:]:
        review = confirm_snapshot_metric(review, metric_key)

    workpaper = build_exportable_review_workpaper(
        review,
        exported_at="2026-08-30T13:00:00+00:00",
    )
    serialised = serialise_review_workpaper(workpaper)

    assert review["status"] == "review_complete"
    assert workpaper["controls"] == {
        "all_core_metrics_decided": True,
        "automatic_extraction_is_verification": False,
        "source_pdf_embedded": False,
    }
    assert workpaper["metrics"][0]["original_value_yuan"] == 10_000_000
    assert workpaper["metrics"][0]["effective_value_yuan"] == 11_000_000
    assert workpaper["ratios"]["net_profit_margin"] == pytest.approx(
        1_000_000 / 11_000_000
    )
    assert "%PDF" not in serialised
    assert len(serialised.encode("utf-8")) < 64 * 1024


@pytest.mark.parametrize('profit,cash,expected', [
    (-100, -200, None), (-100, 200, None), (0, 200, None),
    (100, -200, -2.0), (100, 200, 2.0),
])
def test_cash_conversion_consistent_before_and_after_human_review(profit, cash, expected):
    candidate = _legacy_candidate()
    candidate['values']['current_net_profit'] = profit
    candidate['values']['current_operating_cash_flow'] = cash
    snapshot = build_on_demand_financial_snapshot(_company(), candidate)
    review = build_financial_snapshot_review(snapshot)
    for key in CORE_METRIC_KEYS:
        review = confirm_snapshot_metric(review, key)
    workpaper = build_exportable_review_workpaper(review)
    assert snapshot['ratios']['operating_cash_conversion'] == expected
    assert workpaper['ratios']['operating_cash_conversion'] == expected
    assert next(m for m in workpaper['metrics'] if m['key'] == 'net_profit')['effective_value_yuan'] == profit * 10_000
    assert '净利润不大于零' in serialise_review_workpaper(workpaper)


def test_correcting_profit_to_loss_recomputes_ratio_without_rewriting_candidate():
    snapshot = _snapshot()
    review = build_financial_snapshot_review(snapshot)
    review = correct_snapshot_metric(review, 'net_profit', -100, '按原文核对后更正为亏损。')
    for key in CORE_METRIC_KEYS:
        if key != 'net_profit':
            review = confirm_snapshot_metric(review, key)
    workpaper = build_exportable_review_workpaper(review)
    assert workpaper['ratios']['operating_cash_conversion'] is None
    assert snapshot['ratios']['operating_cash_conversion'] == 1.25
    assert workpaper['ratios']['net_profit_margin'] < 0


def test_missing_automatic_value_may_be_corrected_or_rejected_not_confirmed() -> None:
    snapshot = _snapshot()
    snapshot["metrics"][0]["current_yuan"] = None
    review = build_financial_snapshot_review(snapshot)

    with pytest.raises(FinancialSnapshotReviewError, match="不能直接确认"):
        confirm_snapshot_metric(review, "revenue")
    corrected = correct_snapshot_metric(
        review,
        "revenue",
        10_000_000,
        "自动提取失败，已人工查看官方年报补录。",
    )
    assert corrected["metrics"][0]["decision"] == "corrected"
