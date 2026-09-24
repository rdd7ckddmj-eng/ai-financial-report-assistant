from __future__ import annotations

from copy import deepcopy
import json

import pytest

from src.financial_snapshot_review import (
    CORE_METRIC_KEYS,
    build_exportable_review_workpaper,
    build_financial_snapshot_review,
    confirm_snapshot_metric,
    correct_snapshot_metric,
    reject_snapshot_metric,
)
from src.research_case import (
    ResearchCaseValidationError,
    apply_case_patch,
    new_research_case,
)
from src.research_case_financial_review_bridge import (
    FINANCIAL_REVIEW_ARTIFACT_PAYLOAD_BYTES,
    build_financial_review_research_case_patch,
)


_EMITTED_AT = "2026-08-30T14:00:00+00:00"


def _company() -> dict[str, str]:
    return {
        "code": "600000",
        "name": "测试公司",
        "exchange": "SH",
        "exchange_name": "上海证券交易所",
        "canonical_code": "600000.SH",
    }


def _case(
    *,
    mode: str = "current",
    as_of_date: str | None = None,
) -> dict[str, object]:
    effective = as_of_date or "2026-08-30"
    return new_research_case(
        "case-financial-review",
        _company(),
        mode=mode,
        as_of_date=as_of_date,
        effective_market_date=effective,
        created_at="2026-08-30T10:00:00+00:00",
    )


def _snapshot(
    *,
    captured_excerpt: bool = True,
    include_pages: bool = True,
) -> dict[str, object]:
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
    for index, key in enumerate(CORE_METRIC_KEYS, start=1):
        value = values[key]
        pages = {"start": 90 + index, "end": 90 + index} if include_pages else None
        metrics.append(
            {
                "key": key,
                "label": labels[key],
                "current_yuan": value,
                "previous_yuan": value * 0.9,
                "change_rate": 1 / 9,
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
                    "excerpt": (
                        f"{labels[key]} 本期 {value / 10_000:.0f} 万元"
                        if captured_excerpt
                        else ""
                    ),
                    "excerpt_status": (
                        "captured" if captured_excerpt else "unavailable_legacy"
                    ),
                },
            }
        )
    return {
        "schema_version": "1.1",
        "generated_at": "2026-08-30T11:00:00+00:00",
        "status": "ready_for_human_review",
        "status_label": "自动检查完成，等待人工复核",
        "company": _company(),
        "report": {
            "report_year": 2025,
            "published_date": "2026-04-20",
            "title": "测试公司2025年年度报告",
            "source_url": "https://static.cninfo.com.cn/finalpage/test-report.PDF",
            "page_count": 200,
        },
        "source_fingerprint_sha256": "a" * 64,
        "statement_checks": {
            "income_statement_reconciled": True,
            "balance_sheet_reconciled": True,
            "cash_flow_statement_reconciled": True,
        },
        "unit": "万元",
        "unit_note": "页面数值已换算为人民币元。",
        "metrics": metrics,
        "ratios": {},
        "limitations": [],
    }


def _workpaper(
    *,
    corrected_key: str | None = None,
    rejected_key: str | None = None,
    captured_excerpt: bool = True,
    include_pages: bool = True,
) -> dict[str, object]:
    review = build_financial_snapshot_review(
        _snapshot(
            captured_excerpt=captured_excerpt,
            include_pages=include_pages,
        ),
        review_id="review-gated-1",
        created_at="2026-08-30T11:30:00+00:00",
    )
    for index, key in enumerate(CORE_METRIC_KEYS, start=1):
        if key == corrected_key:
            original = next(
                metric["original_value_yuan"]
                for metric in review["metrics"]
                if metric["key"] == key
            )
            review = correct_snapshot_metric(
                review,
                key,
                float(original) + 123_456,
                "已对照官方年报原文人工更正。",
                decided_at=f"2026-08-30T12:0{index}:00+00:00",
            )
        elif key == rejected_key:
            review = reject_snapshot_metric(
                review,
                key,
                "页面排版无法可靠识别，原值不应使用。",
                decided_at=f"2026-08-30T12:0{index}:00+00:00",
            )
        else:
            review = confirm_snapshot_metric(
                review,
                key,
                decided_at=f"2026-08-30T12:0{index}:00+00:00",
            )
    return build_exportable_review_workpaper(
        review,
        exported_at="2026-08-30T13:00:00+00:00",
    )


def _patch(
    case: dict[str, object],
    workpaper: dict[str, object],
) -> dict[str, object]:
    return build_financial_review_research_case_patch(
        case,
        workpaper,
        patch_id="patch-financial-review-1",
        emitted_at=_EMITTED_AT,
    )


def test_all_confirmed_workpaper_becomes_compact_traceable_case_patch() -> None:
    case = _case()
    original_case = deepcopy(case)

    patch = _patch(case, _workpaper())
    applied = apply_case_patch(case, patch)

    assert case == original_case
    assert patch["source_module"] == "financial_snapshot"
    assert patch["artifact"]["review_status"] == "confirmed"
    assert len(patch["evidence"]) == 5
    assert {
        item["review_status"] for item in patch["evidence"]
    } == {"confirmed"}
    assert all(item["source_tier"] == "official_disclosure" for item in patch["evidence"])
    revenue = next(item for item in patch["evidence"] if "营业收入" in item["title"])
    assert revenue["page_start"] == 91
    assert revenue["excerpt"].startswith("营业收入")
    assert revenue["original_value"] == "1,000"
    assert revenue["unit"] == "万元"
    assert applied["revision"] == 1
    assert applied["questions"]["financial_quality"]["status"] == "answered"
    assert applied["case_brief"]["next_action"]["module"] == "financial_trend"
    payload = patch["artifact"]["payload"]
    assert len(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    ) <= FINANCIAL_REVIEW_ARTIFACT_PAYLOAD_BYTES
    assert "%PDF" not in repr(patch)


def test_corrected_metric_uses_human_value_and_preserves_original_provenance() -> None:
    patch = _patch(_case(), _workpaper(corrected_key="revenue"))

    revenue_evidence = next(
        item for item in patch["evidence"] if "营业收入" in item["title"]
    )
    revenue_payload = next(
        item
        for item in patch["artifact"]["payload"]["metrics"]
        if item["key"] == "revenue"
    )
    assert revenue_evidence["review_status"] == "corrected"
    assert revenue_evidence["original_value"] == "1,000"
    assert "人工更正后的标准化值" in revenue_evidence["basis"]
    assert "更正理由" in revenue_evidence["basis"]
    assert revenue_payload["original_value_yuan"] == 10_000_000
    assert revenue_payload["effective_value_yuan"] == 10_123_456
    assert patch["artifact"]["review_status"] == "corrected"


def test_rejected_metric_is_unknown_and_never_becomes_value_or_evidence() -> None:
    patch = _patch(_case(), _workpaper(rejected_key="net_profit"))

    assert len(patch["evidence"]) == 4
    assert all("净利润" not in item["title"] for item in patch["evidence"])
    rejected_payload = next(
        item
        for item in patch["artifact"]["payload"]["metrics"]
        if item["key"] == "net_profit"
    )
    assert rejected_payload["decision"] == "rejected"
    assert "effective_value_yuan" not in rejected_payload
    assert "original_value_yuan" not in rejected_payload
    assert patch["question_updates"]["financial_quality"]["status"] == "blocked"
    assert patch["case_brief_update"]["next_action"]["module"] == "annual_report"
    assert any(
        "净利润" in item["summary"] and "不得用于" in item["summary"]
        for item in patch["case_brief_update"]["unknowns"]
    )
    assert patch["artifact"]["payload"]["ratios"]["net_profit_margin"] is None
    apply_case_patch(_case(), patch)


def test_legacy_missing_excerpt_is_explicit_and_never_fabricated() -> None:
    patch = _patch(_case(), _workpaper(captured_excerpt=False))

    assert all("excerpt" not in item for item in patch["evidence"])
    assert all(
        "本项未保留原文摘录" in item["basis"]
        for item in patch["evidence"]
    )
    assert patch["question_updates"]["financial_quality"]["status"] == "in_progress"
    assert patch["case_brief_update"]["next_action"]["module"] == "annual_report"
    assert any(
        "以下指标未保留原文摘录，仍需回到官方年报人工定位：" in item["summary"]
        for item in patch["case_brief_update"]["unknowns"]
    )


def test_missing_pages_are_explicit_unknowns_not_invented_page_numbers() -> None:
    patch = _patch(_case(), _workpaper(include_pages=False))

    assert all("page_start" not in item and "page_end" not in item for item in patch["evidence"])
    assert all("页码未保留" in item["basis"] for item in patch["evidence"])
    assert any(
        "未保留有效页码" in item["summary"]
        for item in patch["case_brief_update"]["unknowns"]
    )


def test_pending_review_or_tampered_export_controls_cannot_write() -> None:
    pending_review = build_financial_snapshot_review(_snapshot())
    with pytest.raises(ResearchCaseValidationError, match="导出门槛"):
        _patch(_case(), pending_review)

    workpaper = _workpaper()
    workpaper["controls"]["all_core_metrics_decided"] = False
    with pytest.raises(ResearchCaseValidationError, match="完整导出控制"):
        _patch(_case(), workpaper)


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda workpaper: workpaper["report"].update(
                source_url="https://example.com/not-official.pdf"
            ),
            "官方披露链接",
        ),
        (
            lambda workpaper: workpaper["metrics"][0]["source"].update(
                pages={"start": 0, "end": 1}
            ),
            "页码区间",
        ),
        (
            lambda workpaper: workpaper["metrics"][0]["source"].update(
                excerpt="", excerpt_status="captured"
            ),
            "原文摘录为空",
        ),
        (
            lambda workpaper: workpaper["ratios"].update(
                net_profit_margin=9.99
            ),
            "基础数值不一致",
        ),
    ],
)
def test_tampered_source_or_python_ratio_is_rejected(mutator, message: str) -> None:
    workpaper = _workpaper()
    mutator(workpaper)
    with pytest.raises(ResearchCaseValidationError, match=message):
        _patch(_case(), workpaper)


def test_tampered_rejected_metric_cannot_reintroduce_a_numeric_value() -> None:
    workpaper = _workpaper(rejected_key="net_profit")
    rejected = next(
        item for item in workpaper["metrics"] if item["key"] == "net_profit"
    )
    rejected["effective_value_yuan"] = 999.0

    with pytest.raises(ResearchCaseValidationError, match="不得保留可用数值"):
        _patch(_case(), workpaper)


def test_later_rejection_cannot_silently_leave_previously_accepted_evidence() -> None:
    case = _case()
    case = apply_case_patch(case, _patch(case, _workpaper()))

    with pytest.raises(ResearchCaseValidationError, match="此前已写入有效证据"):
        build_financial_review_research_case_patch(
            case,
            _workpaper(rejected_key="net_profit"),
            patch_id="patch-financial-review-2",
            emitted_at="2026-08-30T15:00:00+00:00",
        )


def test_resolved_rejection_removes_this_reviews_unknown_and_adds_evidence() -> None:
    case = _case()
    case = apply_case_patch(
        case,
        _patch(case, _workpaper(rejected_key="net_profit")),
    )
    assert any(
        "净利润" in item["summary"] for item in case["case_brief"]["unknowns"]
    )

    followup = build_financial_review_research_case_patch(
        case,
        _workpaper(),
        patch_id="patch-financial-review-2",
        emitted_at="2026-08-30T15:00:00+00:00",
    )
    updated = apply_case_patch(case, followup)

    assert len(updated["evidence"]) == 5
    assert not any(
        "净利润" in item["summary"] and "自动提取值已被人工驳回" in item["summary"]
        for item in updated["case_brief"]["unknowns"]
    )


def test_company_and_historical_cutoff_are_enforced() -> None:
    mismatch = _workpaper()
    mismatch["company"]["canonical_code"] = "000001.SZ"
    with pytest.raises(ResearchCaseValidationError, match="公司不匹配"):
        _patch(_case(), mismatch)

    historical_case = _case(mode="historical", as_of_date="2025-12-31")
    with pytest.raises(ResearchCaseValidationError, match="截止日之后"):
        _patch(historical_case, _workpaper())


def test_invalid_excerpt_status_and_binary_payload_fail_closed() -> None:
    invalid_status = _workpaper()
    invalid_status["metrics"][0]["source"]["excerpt_status"] = "guessed"
    with pytest.raises(ResearchCaseValidationError, match="摘录状态无效"):
        _patch(_case(), invalid_status)

    binary = _workpaper()
    binary["report"]["pdf_bytes"] = b"%PDF-secret"
    with pytest.raises(ResearchCaseValidationError, match="不得包含PDF"):
        _patch(_case(), binary)
