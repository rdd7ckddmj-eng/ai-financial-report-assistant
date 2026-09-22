"""Pure human-review workflow for an extracted annual-report snapshot.

Extraction never means verification.  This module preserves the immutable
source candidate, records an explicit decision for every core metric, and
opens the export gate only after all five decisions are complete.  It stores
short text evidence and fingerprints, never source PDF bytes.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from src.bank_statement_extractor import BANK_TEMPLATE
from src.financial_sector_policy import is_special_financial_template


REVIEW_SCHEMA_VERSION = "1.0"
WORKPAPER_SCHEMA_VERSION = "1.0"
CORE_METRIC_KEYS = (
    "revenue",
    "net_profit",
    "operating_cash_flow",
    "total_assets",
    "total_liabilities",
)
DECISIONS = {"pending", "confirmed", "corrected", "rejected"}
MAX_EXCERPT_CHARS = 480
MAX_REASON_CHARS = 240
MAX_REVIEW_BYTES = 64 * 1024


class FinancialSnapshotReviewError(ValueError):
    """Raised when a review decision would weaken the audit trail."""


def _iso_datetime(value: datetime | str | None) -> str:
    candidate: datetime
    if value is None:
        candidate = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        candidate = value
    else:
        try:
            candidate = datetime.fromisoformat(str(value))
        except ValueError as error:
            raise FinancialSnapshotReviewError("复核时间格式无效。") from error
    if candidate.tzinfo is None:
        candidate = candidate.replace(tzinfo=timezone.utc)
    return candidate.astimezone(timezone.utc).isoformat(timespec="seconds")


def _finite_optional(value: object, field: str) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise FinancialSnapshotReviewError(f"{field}必须是有限数字。") from error
    if not math.isfinite(number):
        raise FinancialSnapshotReviewError(f"{field}必须是有限数字。")
    return number


def _required_reason(value: object) -> str:
    reason = " ".join(str(value or "").split())
    if not reason:
        raise FinancialSnapshotReviewError("更正或驳回必须填写理由。")
    if len(reason) > MAX_REASON_CHARS:
        raise FinancialSnapshotReviewError(
            f"复核理由不得超过{MAX_REASON_CHARS}个字符。"
        )
    return reason


def _assert_no_binary(value: object, path: str = "review") -> None:
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise FinancialSnapshotReviewError(f"{path}不得保留PDF或其他二进制本体。")
    if isinstance(value, Mapping):
        for key, child in value.items():
            _assert_no_binary(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _assert_no_binary(child, f"{path}[{index}]")


def _json_size(value: Mapping[str, object]) -> int:
    return len(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    )


def _normalise_source(metric: Mapping[str, object]) -> dict[str, object]:
    raw = metric.get("source")
    source = raw if isinstance(raw, Mapping) else {}
    excerpt = " ".join(str(source.get("excerpt", "")).split())
    if len(excerpt) > MAX_EXCERPT_CHARS:
        excerpt = excerpt[: MAX_EXCERPT_CHARS - 1].rstrip() + "…"
    excerpt_status = str(source.get("excerpt_status", "")).strip()
    if not excerpt:
        excerpt_status = "unavailable_legacy"
    pages = source.get("pages", metric.get("pages"))
    clean_pages: dict[str, int] | None = None
    if isinstance(pages, Mapping):
        try:
            start, end = int(pages["start"]), int(pages["end"])
        except (KeyError, TypeError, ValueError):
            pass
        else:
            if start > 0 and end >= start:
                clean_pages = {"start": start, "end": end}
    return {
        "raw_current_value": _finite_optional(
            source.get("raw_current_value"), "原始本期数值"
        ),
        "raw_previous_value": _finite_optional(
            source.get("raw_previous_value"), "原始比较期数值"
        ),
        "original_unit": str(source.get("original_unit", "")).strip(),
        "accounting_basis": str(
            source.get("accounting_basis", "报表口径待人工确认")
        ).strip()
        or "报表口径待人工确认",
        "comparison_basis": str(
            source.get(
                "comparison_basis",
                "本期与年报比较栏原值；可能包含追溯调整",
            )
        ).strip(),
        "statement": str(
            source.get("statement", metric.get("statement", ""))
        ).strip(),
        "pages": clean_pages,
        "excerpt": excerpt,
        "excerpt_status": excerpt_status or "captured",
    }


def _calculate_review_status(metrics: list[Mapping[str, object]]) -> str:
    decisions = {str(metric.get("decision")) for metric in metrics}
    if "pending" in decisions:
        return "pending_human_review"
    if "rejected" in decisions:
        return "review_complete_with_rejections"
    return "review_complete"


def build_financial_snapshot_review(
    snapshot: Mapping[str, object],
    *,
    review_id: str | None = None,
    created_at: datetime | str | None = None,
) -> dict[str, object]:
    """Create five pending decisions without treating extraction as review."""
    _assert_no_binary(snapshot, "snapshot")
    raw_metrics = snapshot.get("metrics")
    if not isinstance(raw_metrics, list):
        raise FinancialSnapshotReviewError("财务快照缺少核心指标。")
    metrics_by_key = {
        str(metric.get("key")): metric
        for metric in raw_metrics
        if isinstance(metric, Mapping)
    }
    if set(metrics_by_key) != set(CORE_METRIC_KEYS):
        raise FinancialSnapshotReviewError("财务快照必须包含五项且仅包含五项核心指标。")
    company = snapshot.get("company")
    report = snapshot.get("report")
    if not isinstance(company, Mapping) or not isinstance(report, Mapping):
        raise FinancialSnapshotReviewError("财务快照缺少公司或年报身份。")

    review_metrics: list[dict[str, object]] = []
    for key in CORE_METRIC_KEYS:
        metric = metrics_by_key[key]
        review_metrics.append(
            {
                "key": key,
                "label": str(metric.get("label", key)),
                "original_value_yuan": _finite_optional(
                    metric.get("current_yuan"), "自动提取标准化数值"
                ),
                "source": _normalise_source(metric),
                "decision": "pending",
                "corrected_value_yuan": None,
                "reason": "",
                "decided_at": None,
            }
        )
    review: dict[str, object] = {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "review_id": review_id or f"snapshot-review:{uuid4().hex}",
        "created_at": _iso_datetime(created_at),
        "updated_at": _iso_datetime(created_at),
        "status": "pending_human_review",
        "company": {str(key): str(value) for key, value in company.items()},
        "report": deepcopy(dict(report)),
        "source_fingerprint_sha256": str(
            snapshot.get("source_fingerprint_sha256", "")
        ),
        "metrics": review_metrics,
        "decision_history": [],
    }
    validate_financial_snapshot_review(review)
    return review


def validate_financial_snapshot_review(review: Mapping[str, object]) -> None:
    """Validate the bounded review contract and its source evidence."""
    _assert_no_binary(review)
    if review.get("schema_version") != REVIEW_SCHEMA_VERSION:
        raise FinancialSnapshotReviewError("人工复核schema版本不受支持。")
    metrics = review.get("metrics")
    if not isinstance(metrics, list) or len(metrics) != len(CORE_METRIC_KEYS):
        raise FinancialSnapshotReviewError("人工复核必须保留五项核心指标。")
    if [metric.get("key") for metric in metrics] != list(CORE_METRIC_KEYS):
        raise FinancialSnapshotReviewError("人工复核指标顺序或键值无效。")
    for metric in metrics:
        if not isinstance(metric, Mapping):
            raise FinancialSnapshotReviewError("人工复核指标结构无效。")
        decision = metric.get("decision")
        if decision not in DECISIONS:
            raise FinancialSnapshotReviewError("人工复核决策无效。")
        source = metric.get("source")
        if not isinstance(source, Mapping):
            raise FinancialSnapshotReviewError("人工复核缺少原始证据。")
        excerpt = str(source.get("excerpt", ""))
        if len(excerpt) > MAX_EXCERPT_CHARS:
            raise FinancialSnapshotReviewError("原文摘录超过长度限制。")
        if decision == "corrected":
            if _finite_optional(
                metric.get("corrected_value_yuan"), "修改值"
            ) is None:
                raise FinancialSnapshotReviewError("更正必须填写修改值。")
            _required_reason(metric.get("reason"))
        elif decision == "rejected":
            _required_reason(metric.get("reason"))
            if metric.get("corrected_value_yuan") is not None:
                raise FinancialSnapshotReviewError("驳回记录不能同时保存修改值。")
        elif decision == "confirmed":
            if metric.get("original_value_yuan") is None:
                raise FinancialSnapshotReviewError("缺失的自动提取值不能直接确认。")
            if metric.get("corrected_value_yuan") is not None:
                raise FinancialSnapshotReviewError("确认记录不能同时保存修改值。")
    expected_status = _calculate_review_status(metrics)
    if review.get("status") != expected_status:
        raise FinancialSnapshotReviewError("人工复核状态与逐项决策不一致。")
    if _json_size(review) > MAX_REVIEW_BYTES:
        raise FinancialSnapshotReviewError("人工复核底稿超过64KB紧凑上限。")


def decide_financial_snapshot_metric(
    review: Mapping[str, object],
    metric_key: str,
    decision: str,
    *,
    corrected_value_yuan: float | None = None,
    reason: str | None = None,
    decided_at: datetime | str | None = None,
) -> dict[str, object]:
    """Return a new review with one explicit confirm/correct/reject decision."""
    validate_financial_snapshot_review(review)
    if metric_key not in CORE_METRIC_KEYS:
        raise FinancialSnapshotReviewError("待复核指标不存在。")
    decision_map = {
        "confirm": "confirmed",
        "correct": "corrected",
        "reject": "rejected",
    }
    stored_decision = decision_map.get(decision)
    if stored_decision is None:
        raise FinancialSnapshotReviewError("决策只能是confirm、correct或reject。")
    timestamp = _iso_datetime(decided_at)
    work = deepcopy(dict(review))
    metric = next(
        item for item in work["metrics"] if item["key"] == metric_key
    )
    original_decision = str(metric["decision"])
    original_value = _finite_optional(
        metric.get("original_value_yuan"), "原始标准化数值"
    )
    if stored_decision == "confirmed":
        if original_value is None:
            raise FinancialSnapshotReviewError("缺失的自动提取值不能直接确认。")
        if corrected_value_yuan is not None or str(reason or "").strip():
            raise FinancialSnapshotReviewError("确认原值时不得附带修改值或修改理由。")
        metric.update(
            corrected_value_yuan=None,
            reason="",
        )
    elif stored_decision == "corrected":
        corrected = _finite_optional(corrected_value_yuan, "修改值")
        if corrected is None:
            raise FinancialSnapshotReviewError("更正必须填写修改值。")
        if original_value is not None and math.isclose(
            corrected, original_value, rel_tol=0.0, abs_tol=1e-9
        ):
            raise FinancialSnapshotReviewError("修改值与原值相同，请选择确认。")
        metric.update(
            corrected_value_yuan=corrected,
            reason=_required_reason(reason),
        )
    else:
        if corrected_value_yuan is not None:
            raise FinancialSnapshotReviewError("驳回不能填写修改值。")
        metric.update(
            corrected_value_yuan=None,
            reason=_required_reason(reason),
        )
    metric["decision"] = stored_decision
    metric["decided_at"] = timestamp
    work["decision_history"].append(
        {
            "metric_key": metric_key,
            "from": original_decision,
            "to": stored_decision,
            "decided_at": timestamp,
            "reason": str(metric["reason"]),
        }
    )
    work["updated_at"] = timestamp
    work["status"] = _calculate_review_status(work["metrics"])
    validate_financial_snapshot_review(work)
    return work


def confirm_snapshot_metric(
    review: Mapping[str, object],
    metric_key: str,
    *,
    decided_at: datetime | str | None = None,
) -> dict[str, object]:
    """Confirm the immutable extracted value for one metric."""
    return decide_financial_snapshot_metric(
        review, metric_key, "confirm", decided_at=decided_at
    )


def correct_snapshot_metric(
    review: Mapping[str, object],
    metric_key: str,
    corrected_value_yuan: float,
    reason: str,
    *,
    decided_at: datetime | str | None = None,
) -> dict[str, object]:
    """Record a corrected value while preserving the extracted original."""
    return decide_financial_snapshot_metric(
        review,
        metric_key,
        "correct",
        corrected_value_yuan=corrected_value_yuan,
        reason=reason,
        decided_at=decided_at,
    )


def reject_snapshot_metric(
    review: Mapping[str, object],
    metric_key: str,
    reason: str,
    *,
    decided_at: datetime | str | None = None,
) -> dict[str, object]:
    """Reject one unusable extraction without inventing a replacement."""
    return decide_financial_snapshot_metric(
        review,
        metric_key,
        "reject",
        reason=reason,
        decided_at=decided_at,
    )


def _effective_value(metric: Mapping[str, object]) -> float | None:
    if metric.get("decision") == "confirmed":
        return _finite_optional(metric.get("original_value_yuan"), "确认值")
    if metric.get("decision") == "corrected":
        return _finite_optional(metric.get("corrected_value_yuan"), "修改值")
    return None


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    # Use the same denominator rule as candidate snapshots and public history.
    if numerator is None or denominator is None or denominator <= 0:
        return None
    result = numerator / denominator
    return result if math.isfinite(result) else None


def build_exportable_review_workpaper(
    review: Mapping[str, object],
    *,
    exported_at: datetime | str | None = None,
) -> dict[str, object]:
    """Open the export gate only after every core metric has a decision."""
    validate_financial_snapshot_review(review)
    if review.get("status") == "pending_human_review":
        raise FinancialSnapshotReviewError("五项核心数字尚未全部完成复核决策。")
    metrics: list[dict[str, object]] = []
    effective: dict[str, float | None] = {}
    for raw_metric in review["metrics"]:
        metric = deepcopy(dict(raw_metric))
        value = _effective_value(metric)
        metric["effective_value_yuan"] = value
        effective[str(metric["key"])] = value
        metrics.append(metric)
    workpaper: dict[str, object] = {
        "schema_version": WORKPAPER_SCHEMA_VERSION,
        "workpaper_type": "annual_report_human_review",
        "exported_at": _iso_datetime(exported_at),
        "review_id": review["review_id"],
        "review_status": review["status"],
        "company": deepcopy(review["company"]),
        "report": deepcopy(review["report"]),
        "source_fingerprint_sha256": review["source_fingerprint_sha256"],
        "metrics": metrics,
        "ratio_policy": "比例仅在分母为正且有效金额可用时计算；净利润不大于零时不展示现金利润比。缺失或不可计算的比例保留为空，原始金额与复核决定不变。",
        "ratios": ({key: None for key in ('net_profit_margin', 'operating_cash_conversion', 'liabilities_to_assets')}
                   if is_special_financial_template(review['report'].get('statement_template')) else {
            "net_profit_margin": _safe_ratio(
                effective["net_profit"], effective["revenue"]
            ),
            "operating_cash_conversion": _safe_ratio(
                effective["operating_cash_flow"], effective["net_profit"]
            ),
            "liabilities_to_assets": _safe_ratio(
                effective["total_liabilities"], effective["total_assets"]
            ),
        }),
        "controls": {
            "all_core_metrics_decided": True,
            "automatic_extraction_is_verification": False,
            "source_pdf_embedded": False,
        },
    }
    if is_special_financial_template(review['report'].get('statement_template')):
        workpaper['ratio_policy'] = '金融机构模板不计算普通公司比例；已复核金额不等于行业监管指标或风险结论。'
    _assert_no_binary(workpaper, "workpaper")
    if _json_size(workpaper) > MAX_REVIEW_BYTES:
        raise FinancialSnapshotReviewError("可导出复核底稿超过64KB紧凑上限。")
    return workpaper


def serialise_review_workpaper(workpaper: Mapping[str, object]) -> str:
    """Serialise a previously gated workpaper as stable UTF-8 JSON."""
    _assert_no_binary(workpaper, "workpaper")
    if workpaper.get("workpaper_type") != "annual_report_human_review":
        raise FinancialSnapshotReviewError("不是可导出的年报人工复核底稿。")
    return json.dumps(workpaper, ensure_ascii=False, indent=2, sort_keys=True)
