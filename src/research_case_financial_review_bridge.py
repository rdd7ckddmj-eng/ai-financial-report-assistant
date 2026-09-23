"""Write one gated annual-report human review into a ResearchCase.

The bridge accepts only the compact workpaper produced after all five core
metrics have an explicit human decision.  Confirmed and corrected metrics
become traceable evidence; rejected metrics remain explicit unknowns and are
never promoted to usable financial values.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
import hashlib
import json
import math
import re
from src.bank_statement_extractor import BANK_TEMPLATE
from src.financial_sector_policy import is_special_financial_template
from src.pdf_text_derivation import compact_report_text_adjustments
from typing import Any

from src.financial_snapshot_review import (
    CORE_METRIC_KEYS,
    WORKPAPER_SCHEMA_VERSION,
)
from src.research_case import (
    MAX_UNKNOWNS,
    ResearchCaseCapacityError,
    ResearchCaseValidationError,
    apply_case_patch,
    is_allowed_evidence_url,
    validate_research_case,
)


FINANCIAL_REVIEW_ARTIFACT_PAYLOAD_BYTES = 8_000
MAX_REVIEW_EXCERPT_CHARS = 480
_FINAL_REVIEW_STATUSES = {
    "review_complete",
    "review_complete_with_rejections",
}
_FINAL_DECISIONS = {"confirmed", "corrected", "rejected"}
_EXCERPT_STATUSES = {"captured", "unavailable_legacy"}
_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def _error(message: str) -> ResearchCaseValidationError:
    return ResearchCaseValidationError(message)


def _compact_text(value: object, *, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split()).strip()[:limit]


def _required_text(value: object, *, field: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error(f"{field}必须是非空文本。")
    cleaned = value.strip()
    if len(cleaned) > limit:
        raise _error(f"{field}超过{limit}个字符。")
    return cleaned


def _iso_date(value: object, *, field: str) -> str:
    text = _required_text(value, field=field, limit=10)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise _error(f"{field}必须使用YYYY-MM-DD格式。") from exc
    if parsed.isoformat() != text:
        raise _error(f"{field}必须使用YYYY-MM-DD格式。")
    return text


def _iso_datetime(value: object, *, field: str) -> str:
    text = _required_text(value, field=field, limit=50)
    if "T" not in text:
        raise _error(f"{field}必须是ISO日期时间。")
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _error(f"{field}必须是ISO日期时间。") from exc
    return text


def _finite(value: object, *, field: str, optional: bool = False) -> float | None:
    if value is None and optional:
        return None
    if isinstance(value, bool):
        raise _error(f"{field}必须是有限数字。")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise _error(f"{field}必须是有限数字。") from exc
    if not math.isfinite(number):
        raise _error(f"{field}必须是有限数字。")
    return number


def _assert_compact_json(value: object, path: str = "workpaper") -> None:
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise _error(f"{path}不得包含PDF或其他二进制本体。")
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _error(f"{path}不得包含NaN或Infinity。")
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise _error(f"{path}的对象键必须是文本。")
            _assert_compact_json(child, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _assert_compact_json(child, f"{path}[{index}]")
        return
    raise _error(f"{path}只能包含标准JSON值。")


def _payload_size(value: object) -> int:
    _assert_compact_json(value, "artifact.payload")
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )


def _identifier(prefix: str, *parts: object) -> str:
    material = "\x1f".join(
        part if isinstance(part, str) else "" for part in parts
    ).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(material).hexdigest()[:24]}"


def _normalise_pages(value: object, *, metric_key: str) -> dict[str, int] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) != {"start", "end"}:
        raise _error(f"{metric_key}的页码区间无效。")
    start, end = value.get("start"), value.get("end")
    if (
        isinstance(start, bool)
        or not isinstance(start, int)
        or start <= 0
        or isinstance(end, bool)
        or not isinstance(end, int)
        or end < start
    ):
        raise _error(f"{metric_key}的页码区间无效。")
    return {"start": start, "end": end}


def _same_number(left: object, right: object) -> bool:
    left_number = _finite(left, field="复核数值", optional=True)
    right_number = _finite(right, field="复核数值", optional=True)
    if left_number is None or right_number is None:
        return left_number is right_number
    return math.isclose(left_number, right_number, rel_tol=0.0, abs_tol=1e-9)


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    result = numerator / denominator
    return result if math.isfinite(result) else None


def _validate_ratio(value: object, expected: float | None, *, field: str) -> None:
    if expected is None:
        if value is not None:
            raise _error(f"{field}在基础数值不可用时必须为null。")
        return
    actual = _finite(value, field=field)
    if actual is None or not math.isclose(
        actual, expected, rel_tol=1e-12, abs_tol=1e-12
    ):
        raise _error(f"{field}与人工复核后的基础数值不一致。")


def _validate_workpaper(
    case: Mapping[str, object],
    workpaper: object,
) -> dict[str, Any]:
    """Validate the export gate and return bounded data used by the patch."""
    if not isinstance(workpaper, Mapping):
        raise _error("年报人工复核底稿必须是对象。")
    _assert_compact_json(workpaper)
    if workpaper.get("schema_version") != WORKPAPER_SCHEMA_VERSION:
        raise _error("年报人工复核底稿schema版本不受支持。")
    if workpaper.get("workpaper_type") != "annual_report_human_review":
        raise _error("只接受已通过导出门槛的年报人工复核底稿。")
    exported_at = _iso_datetime(
        workpaper.get("exported_at"), field="workpaper.exported_at"
    )
    review_id = _required_text(
        workpaper.get("review_id"), field="workpaper.review_id", limit=160
    )
    review_status = workpaper.get("review_status")
    if (
        not isinstance(review_status, str)
        or review_status not in _FINAL_REVIEW_STATUSES
    ):
        raise _error("五项核心数字尚未全部完成复核决策。")

    controls = workpaper.get("controls")
    if not isinstance(controls, Mapping) or dict(controls) != {
        "all_core_metrics_decided": True,
        "automatic_extraction_is_verification": False,
        "source_pdf_embedded": False,
    }:
        raise _error("年报人工复核底稿未通过完整导出控制。")

    company = workpaper.get("company")
    if not isinstance(company, Mapping):
        raise _error("年报人工复核底稿缺少公司身份。")
    canonical_code = _required_text(
        company.get("canonical_code"),
        field="workpaper.company.canonical_code",
        limit=16,
    ).upper()
    if canonical_code != case["company"]["canonical_code"]:
        raise _error("年报人工复核底稿与案件公司不匹配。")

    report = workpaper.get("report")
    if not isinstance(report, Mapping):
        raise _error("年报人工复核底稿缺少报告身份。")
    report_title = _required_text(
        report.get("title"), field="workpaper.report.title", limit=300
    )
    published_date = _iso_date(
        report.get("published_date"), field="workpaper.report.published_date"
    )
    source_url = _required_text(
        report.get("source_url"),
        field="workpaper.report.source_url",
        limit=800,
    )
    if not is_allowed_evidence_url(
        source_url,
        source_tier="official_disclosure",
        company=case["company"],
    ):
        raise _error("年报来源必须是通过白名单校验的官方披露链接。")
    if (
        case["scope"]["mode"] == "historical"
        and published_date > str(case["scope"]["as_of_date"])
    ):
        raise _error("历史案件不能写入截止日之后发布的年报复核底稿。")

    fingerprint = _required_text(
        workpaper.get("source_fingerprint_sha256"),
        field="workpaper.source_fingerprint_sha256",
        limit=64,
    )
    if not _SHA256_PATTERN.fullmatch(fingerprint):
        raise _error("年报证据指纹必须是64位SHA-256十六进制文本。")

    raw_metrics = workpaper.get("metrics")
    if not isinstance(raw_metrics, list) or len(raw_metrics) != len(CORE_METRIC_KEYS):
        raise _error("年报人工复核底稿必须包含五项且仅包含五项核心指标。")
    keys = [
        metric.get("key") if isinstance(metric, Mapping) else None
        for metric in raw_metrics
    ]
    if tuple(keys) != CORE_METRIC_KEYS:
        raise _error("年报人工复核底稿的核心指标顺序或键值无效。")

    metrics: list[dict[str, Any]] = []
    effective: dict[str, float | None] = {}
    rejection_count = 0
    for raw_metric in raw_metrics:
        if not isinstance(raw_metric, Mapping):
            raise _error("年报人工复核指标结构无效。")
        key = str(raw_metric["key"])
        label = _required_text(
            raw_metric.get("label"), field=f"{key}.label", limit=160
        )
        decision = raw_metric.get("decision")
        if not isinstance(decision, str) or decision not in _FINAL_DECISIONS:
            raise _error(f"{key}尚未完成最终复核决策。")
        decided_at = _iso_datetime(
            raw_metric.get("decided_at"), field=f"{key}.decided_at"
        )
        original = _finite(
            raw_metric.get("original_value_yuan"),
            field=f"{key}.original_value_yuan",
            optional=True,
        )
        corrected = _finite(
            raw_metric.get("corrected_value_yuan"),
            field=f"{key}.corrected_value_yuan",
            optional=True,
        )
        effective_value = _finite(
            raw_metric.get("effective_value_yuan"),
            field=f"{key}.effective_value_yuan",
            optional=True,
        )
        reason = _compact_text(raw_metric.get("reason"), limit=240)

        if decision == "confirmed":
            if original is None or corrected is not None or reason:
                raise _error(f"{key}的确认决策与原值或理由不一致。")
            if not _same_number(effective_value, original):
                raise _error(f"{key}的有效值必须等于已确认原值。")
        elif decision == "corrected":
            if corrected is None or not reason:
                raise _error(f"{key}的更正决策必须保留修改值和理由。")
            if original is not None and _same_number(corrected, original):
                raise _error(f"{key}的更正值与原值相同。")
            if not _same_number(effective_value, corrected):
                raise _error(f"{key}的有效值必须等于人工更正值。")
        else:
            rejection_count += 1
            if corrected is not None or effective_value is not None or not reason:
                raise _error(f"{key}被驳回后不得保留可用数值，且必须填写理由。")

        source = raw_metric.get("source")
        if not isinstance(source, Mapping):
            raise _error(f"{key}缺少原始报表证据。")
        raw_current = _finite(
            source.get("raw_current_value"),
            field=f"{key}.source.raw_current_value",
            optional=True,
        )
        raw_previous = _finite(
            source.get("raw_previous_value"),
            field=f"{key}.source.raw_previous_value",
            optional=True,
        )
        pages = _normalise_pages(source.get("pages"), metric_key=key)
        raw_excerpt = source.get("excerpt", "")
        if not isinstance(raw_excerpt, str):
            raise _error(f"{key}的原文摘录必须是文本。")
        excerpt = " ".join(raw_excerpt.split())
        if len(excerpt) > MAX_REVIEW_EXCERPT_CHARS:
            raise _error(f"{key}的原文摘录超过{MAX_REVIEW_EXCERPT_CHARS}个字符。")
        excerpt_status = str(source.get("excerpt_status", "")).strip()
        if excerpt_status not in _EXCERPT_STATUSES:
            raise _error(f"{key}的原文摘录状态无效。")
        if excerpt_status == "captured" and not excerpt:
            raise _error(f"{key}标记已捕获原文，但原文摘录为空。")
        if excerpt_status == "unavailable_legacy" and excerpt:
            raise _error(f"{key}是旧快照无原文状态，不能伪造原文摘录。")

        metrics.append(
            {
                "key": key,
                "label": label,
                "decision": str(decision),
                "decided_at": decided_at,
                "original_value_yuan": original,
                "corrected_value_yuan": corrected,
                "effective_value_yuan": effective_value,
                "reason": reason,
                "source": {
                    "raw_current_value": raw_current,
                    "raw_previous_value": raw_previous,
                    "original_unit": _compact_text(
                        source.get("original_unit"), limit=80
                    ),
                    "accounting_basis": _compact_text(
                        source.get("accounting_basis"), limit=240
                    ) or "报表口径待人工确认",
                    "comparison_basis": _compact_text(
                        source.get("comparison_basis"), limit=320
                    ),
                    "comparison_comparable": source.get("comparison_comparable", True) is not False,
                    "statement": _compact_text(
                        source.get("statement"), limit=120
                    ),
                    "pages": pages,
                    "excerpt": excerpt,
                    "excerpt_status": excerpt_status,
                },
            }
        )
        effective[key] = effective_value

    expected_status = (
        "review_complete_with_rejections"
        if rejection_count
        else "review_complete"
    )
    if review_status != expected_status:
        raise _error("年报人工复核底稿状态与逐项决策不一致。")

    ratios = workpaper.get("ratios")
    if not isinstance(ratios, Mapping):
        raise _error("年报人工复核底稿缺少程序计算比率。")
    expected_ratios = {
        "net_profit_margin": _safe_ratio(
            effective["net_profit"], effective["revenue"]
        ),
        "operating_cash_conversion": _safe_ratio(
            effective["operating_cash_flow"], effective["net_profit"]
        ),
        "liabilities_to_assets": _safe_ratio(
            effective["total_liabilities"], effective["total_assets"]
        ),
    }
    if set(ratios) != set(expected_ratios):
        raise _error("年报人工复核底稿的程序计算比率字段不完整。")
    if is_special_financial_template(report.get('statement_template')):
        expected_ratios = {key: None for key in expected_ratios}
    for key, expected in expected_ratios.items():
        _validate_ratio(ratios.get(key), expected, field=f"ratios.{key}")

    try:
        text_adjustments = compact_report_text_adjustments(report)
    except ValueError as error:
        raise _error(str(error)) from error

    return {
        "exported_at": exported_at,
        "review_id": review_id,
        "review_status": str(review_status),
        "company_id": canonical_code,
        "report": {
            "statement_template": report.get('statement_template', 'general'),
            "report_year": report.get("report_year"),
            "title": report_title,
            "published_date": published_date,
            "source_url": source_url,
            **({'text_adjustments': text_adjustments,
                'text_derivation_note': '此处保留负号连接摘要；完整坐标记录在原复核底稿中，原PDF未修改。'}
               if text_adjustments else {}),
        },
        "fingerprint": fingerprint.lower(),
        "metrics": metrics,
        "ratios": expected_ratios,
    }


def _format_number(value: float) -> str:
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def _source_basis(metric: Mapping[str, Any]) -> str:
    source = metric["source"]
    parts = [
        source.get("statement") or "报表名称待核验",
        source.get("accounting_basis") or "报表口径待人工确认",
    ]
    if source.get("comparison_basis"):
        parts.append(source["comparison_basis"])
    pages = source.get("pages")
    if pages is None:
        parts.append("页码未保留，需回到官方年报定位")
    if source.get("excerpt_status") == "unavailable_legacy":
        parts.append("旧版快照未保留原文摘录，未生成或补写摘录")
    if metric["decision"] == "corrected":
        parts.append(
            "人工更正后的标准化值为"
            f"{_format_number(metric['effective_value_yuan'])}元"
        )
        parts.append(f"更正理由：{metric['reason']}")
    else:
        parts.append(
            "人工确认的标准化值为"
            f"{_format_number(metric['effective_value_yuan'])}元"
        )
    return _compact_text("；".join(str(part) for part in parts if part), limit=1_000)


def _original_value(metric: Mapping[str, Any]) -> tuple[str, str] | None:
    source = metric["source"]
    raw = source.get("raw_current_value")
    unit = str(source.get("original_unit", "")).strip()
    if raw is not None:
        return _format_number(float(raw)), unit
    original = metric.get("original_value_yuan")
    if original is not None:
        return _format_number(float(original)), "元（自动标准化值）"
    return None


def _metric_evidence_id(
    case: Mapping[str, object],
    clean: Mapping[str, Any],
    metric_key: str,
) -> str:
    """Keep one stable evidence identity across later review corrections."""
    return _identifier(
        "ev-finreview",
        str(case["case_id"]),
        str(clean["review_id"]),
        str(clean["fingerprint"]),
        metric_key,
    )


def _build_evidence(
    case: Mapping[str, object],
    clean: Mapping[str, Any],
) -> tuple[list[dict[str, object]], dict[str, str]]:
    evidence: list[dict[str, object]] = []
    ids_by_metric: dict[str, str] = {}
    for metric in clean["metrics"]:
        if metric["decision"] == "rejected":
            continue
        key = metric["key"]
        evidence_id = _metric_evidence_id(case, clean, key)
        item: dict[str, object] = {
            "evidence_id": evidence_id,
            "source_module": "financial_snapshot",
            "source_tier": "official_disclosure",
            "title": _compact_text(
                f"{clean['report']['title']}｜{metric['label']}（人工复核）",
                limit=400,
            ),
            "source_url": clean["report"]["source_url"],
            "published_date": clean["report"]["published_date"],
            "review_status": metric["decision"],
            "basis": _source_basis(metric),
        }
        pages = metric["source"]["pages"]
        if pages is not None:
            item["page_start"] = pages["start"]
            item["page_end"] = pages["end"]
        excerpt = metric["source"]["excerpt"]
        if excerpt:
            item["excerpt"] = excerpt
        original = _original_value(metric)
        if original is not None:
            item["original_value"] = original[0]
            if original[1]:
                item["unit"] = original[1]
        evidence.append(item)
        ids_by_metric[key] = evidence_id
    return evidence, ids_by_metric


def _build_unknowns(
    case: Mapping[str, object],
    clean: Mapping[str, Any],
) -> list[dict[str, str]]:
    canonical_code = str(case["company"]["canonical_code"])
    owned_unknown_ids = {
        _identifier(
            "unknown-finreview",
            canonical_code,
            clean["review_id"],
            origin,
        )
        for origin in (
            *(f"rejected:{key}" for key in CORE_METRIC_KEYS),
            "legacy-excerpts",
            "missing-pages",
        )
    }
    # Rebuilding the same review replaces its own current limitations while
    # preserving unknowns created by users or other modules.
    result = [
        {
            "unknown_id": str(item["unknown_id"]),
            "summary": str(item["summary"]),
        }
        for item in case["case_brief"]["unknowns"]
        if str(item["unknown_id"]) not in owned_unknown_ids
    ]
    known_ids = {item["unknown_id"] for item in result}

    def add(origin: str, summary: str) -> None:
        unknown_id = _identifier(
            "unknown-finreview", canonical_code, clean["review_id"], origin
        )
        if unknown_id in known_ids:
            return
        if len(result) >= MAX_UNKNOWNS:
            raise ResearchCaseCapacityError(
                f"case_brief.unknowns已达到容量{MAX_UNKNOWNS}。"
            )
        result.append(
            {
                "unknown_id": unknown_id,
                "summary": _compact_text(summary, limit=1_800),
            }
        )
        known_ids.add(unknown_id)

    legacy_metrics: list[str] = []
    missing_page_metrics: list[str] = []
    for metric in clean["metrics"]:
        if metric["decision"] == "rejected":
            add(
                f"rejected:{metric['key']}",
                f"{metric['label']}仍为未知：该自动提取值已被人工驳回，"
                f"不得用于比率或结论。驳回理由：{metric['reason']}",
            )
        if metric["source"]["excerpt_status"] == "unavailable_legacy":
            legacy_metrics.append(metric["label"])
        if metric["source"]["pages"] is None:
            missing_page_metrics.append(metric["label"])
    if legacy_metrics:
        add(
            "legacy-excerpts",
            "旧版快照未保留以下指标的原文摘录，系统没有伪造摘录，"
            "仍需回到官方年报人工定位：" + "、".join(legacy_metrics) + "。",
        )
    if missing_page_metrics:
        add(
            "missing-pages",
            "以下指标未保留有效页码，仍需回到官方年报人工定位："
            + "、".join(missing_page_metrics)
            + "。",
        )
    return result


def _build_artifact_payload(clean: Mapping[str, Any]) -> dict[str, object]:
    compact_metrics: list[dict[str, object]] = []
    counts = {"confirmed": 0, "corrected": 0, "rejected": 0}
    for metric in clean["metrics"]:
        decision = metric["decision"]
        counts[decision] += 1
        source = metric["source"]
        item: dict[str, object] = {
            "key": metric["key"],
            "label": metric["label"],
            "decision": decision,
            "source": {
                "statement": source["statement"],
                "pages": source["pages"],
                "excerpt_status": source["excerpt_status"],
            },
        }
        if decision == "rejected":
            # A rejected extraction is a review outcome, never a usable value.
            item["reason"] = metric["reason"]
        else:
            item["effective_value_yuan"] = metric["effective_value_yuan"]
            item["original_value_yuan"] = metric["original_value_yuan"]
            if decision == "corrected":
                item["reason"] = metric["reason"]
        compact_metrics.append(item)
    payload: dict[str, object] = {
        "schema": "financial-review-workpaper.v1",
        "company_id": clean["company_id"],
        "report": clean["report"],
        "source_fingerprint_sha256": clean["fingerprint"],
        "review": {
            "review_id": clean["review_id"],
            "status": clean["review_status"],
            "exported_at": clean["exported_at"],
            "counts": counts,
        },
        "metrics": compact_metrics,
        "ratios": clean["ratios"],
        "controls": {
            "human_decision_complete": True,
            "rejected_values_excluded": True,
            "source_pdf_embedded": False,
        },
    }
    if _payload_size(payload) > FINANCIAL_REVIEW_ARTIFACT_PAYLOAD_BYTES:
        raise ResearchCaseCapacityError(
            "年报人工复核artifact.payload超过桥接层8KB限制。"
        )
    return payload


def _merge_references(existing: object, incoming: list[str]) -> list[str]:
    current = [str(item) for item in existing] if isinstance(existing, list) else []
    return list(dict.fromkeys([*current, *incoming]))


def _format_ratio(value: float | None) -> str:
    return "待补证" if value is None else f"{value:.1%}"


def build_financial_review_research_case_patch(
    case: object,
    workpaper: object,
    *,
    patch_id: object,
    emitted_at: object,
) -> dict[str, Any]:
    """Build and preflight a compact ``financial_snapshot`` CasePatch."""
    validate_research_case(case)
    if not isinstance(case, Mapping):  # Static type narrowing after validation.
        raise _error("研究案件必须是对象。")
    clean_patch_id = _required_text(patch_id, field="patch_id", limit=80)
    clean_emitted_at = _iso_datetime(emitted_at, field="emitted_at")
    clean = _validate_workpaper(case, workpaper)

    existing_evidence_ids = {
        str(item["evidence_id"]) for item in case["evidence"]
    }
    for metric in clean["metrics"]:
        if (
            metric["decision"] == "rejected"
            and _metric_evidence_id(case, clean, metric["key"])
            in existing_evidence_ids
        ):
            # CasePatch v1 intentionally has no silent evidence deletion.  A
            # formerly accepted value therefore cannot be made to look absent
            # merely by omitting it from the next patch.
            raise _error(
                f"{metric['label']}此前已写入有效证据，当前版本不能直接改为驳回；"
                "请先使用显式证据撤回流程或新建后续案件。"
            )

    evidence, ids_by_metric = _build_evidence(case, clean)
    artifact_id = _identifier(
        "artifact-finreview",
        str(case["case_id"]),
        str(clean["review_id"]),
        str(clean["fingerprint"]),
    )
    payload = _build_artifact_payload(clean)
    counts = {
        decision: sum(
            metric["decision"] == decision for metric in clean["metrics"]
        )
        for decision in ("confirmed", "corrected", "rejected")
    }
    legacy_count = sum(
        metric["source"]["excerpt_status"] == "unavailable_legacy"
        for metric in clean["metrics"]
    )
    missing_page_count = sum(
        metric["source"]["pages"] is None for metric in clean["metrics"]
    )

    if counts["rejected"]:
        lane_status = "blocked"
        lane_action = "回到官方年报原文，重新定位并补录被驳回的核心数字。"
    elif legacy_count or missing_page_count:
        lane_status = "in_progress"
        lane_action = "回到官方年报补齐缺失的页码或短原文摘录。"
    else:
        lane_status = "answered"
        lane_action = ""
    ratios = clean["ratios"]
    ratio_summary = (
        "金融机构模板不计算普通公司比例；行业监管指标仍需单独核验。"
        if is_special_financial_template(clean['report'].get('statement_template')) else
        f"程序计算净利率{_format_ratio(ratios['net_profit_margin'])}、"
        f"经营现金转换率{_format_ratio(ratios['operating_cash_conversion'])}、"
        f"资产负债率{_format_ratio(ratios['liabilities_to_assets'])}。"
    )
    lane_summary = (
        "五项核心数字已完成人工决策："
        f"确认{counts['confirmed']}项、更正{counts['corrected']}项、"
        f"驳回{counts['rejected']}项；只有确认或更正项计入有效证据。"
        f"{ratio_summary}"
    )

    existing_brief_evidence = case["case_brief"]["evidence"]
    all_artifact_ids = _merge_references(
        existing_brief_evidence["artifact_ids"], [artifact_id]
    )
    new_evidence_ids = [item["evidence_id"] for item in evidence]
    all_evidence_ids = _merge_references(
        existing_brief_evidence["evidence_ids"], new_evidence_ids
    )
    evidence_summary = (
        f"年报五项核心数字已人工复核：{counts['confirmed']}项确认、"
        f"{counts['corrected']}项更正、{counts['rejected']}项驳回；"
        f"{len(evidence)}项可作为官方披露人工复核证据，"
        "被驳回数字未写入有效证据。"
    )
    previous_summary = _compact_text(
        existing_brief_evidence.get("summary"), limit=1_400
    )
    if previous_summary:
        evidence_summary = f"{evidence_summary} 既有案件摘要：{previous_summary}"

    unknowns = _build_unknowns(case, clean)
    if counts["rejected"]:
        primary_question = "被驳回的年报核心数字应如何回到原文补证？"
        next_action = {
            "module": "annual_report",
            "action": "重新定位并复核被驳回的核心数字",
            "reason": "被驳回数字属于未知项，不得进入财务比率或研究结论。",
        }
    elif legacy_count or missing_page_count:
        primary_question = "已复核数字是否有足够的页码与原文证据支持？"
        next_action = {
            "module": "annual_report",
            "action": "补齐缺失的页码与短原文摘录",
            "reason": "旧快照或来源定位不完整，不能伪造缺失的原文证据。",
        }
    else:
        primary_question = (
            case["case_brief"]["primary_question"]
            or "复核后的核心数字揭示了怎样的盈利与现金质量？"
        )
        next_action = {
            "module": "financial_trend",
            "action": "使用复核后的数字核验跨期财务趋势",
            "reason": "五项核心数字已完成人工复核，可继续检查趋势的一致性。",
        }

    existing_question = case["questions"]["financial_quality"]
    question_artifact_ids = _merge_references(
        existing_question["artifact_ids"], [artifact_id]
    )
    question_evidence_ids = _merge_references(
        existing_question["evidence_ids"], new_evidence_ids
    )

    artifact_review_status = (
        "corrected"
        if counts["corrected"] or counts["rejected"]
        else "confirmed"
    )
    patch: dict[str, Any] = {
        "patch_id": clean_patch_id,
        "case_id": case["case_id"],
        "base_revision": case["revision"],
        "canonical_code": case["company"]["canonical_code"],
        "mode": case["scope"]["mode"],
        "as_of_date": case["scope"]["as_of_date"],
        "emitted_at": clean_emitted_at,
        "source_module": "financial_snapshot",
        "artifact": {
            "artifact_id": artifact_id,
            "module": "financial_snapshot",
            "title": f"{case['company']['name']}｜年报五项核心数字人工复核底稿",
            "generated_at": clean_emitted_at,
            "payload": payload,
            "review_status": artifact_review_status,
        },
        "evidence": evidence,
        "case_brief_update": {
            "primary_question": primary_question,
            "evidence": {
                "summary": _compact_text(evidence_summary, limit=3_000),
                "artifact_ids": all_artifact_ids,
                "evidence_ids": all_evidence_ids,
            },
            "unknowns": unknowns,
            "next_action": next_action,
        },
        "question_updates": {
            "financial_quality": {
                "status": lane_status,
                "summary": _compact_text(lane_summary, limit=2_000),
                "next_action": lane_action,
                "artifact_ids": question_artifact_ids,
                "evidence_ids": question_evidence_ids,
            }
        },
        "audit_message": (
            "已写入年报五项核心数字人工复核底稿；"
            "被驳回数值未作为有效证据，且未保存PDF或整页文本。"
        ),
    }

    # Do not return a patch until the canonical reducer has validated every
    # source URL, page range, review status and reference.
    apply_case_patch(case, patch)
    return patch
