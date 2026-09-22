"""Translate one Historical Lens snapshot into a bounded ResearchCase patch.

The bridge is intentionally pure and UI-free.  It persists only the market
state calculated at the requested cut-off and official disclosures that were
published no later than that cut-off.  Later outcome/reveal data is never read,
copied or referenced by this module.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
import math
from typing import Any

from src.research_case import (
    MAX_EVIDENCE,
    ResearchCaseCapacityError,
    ResearchCaseValidationError,
    apply_case_patch,
    is_allowed_evidence_url,
    validate_research_case,
)


HISTORICAL_ARTIFACT_PAYLOAD_BYTES = 4_000
MAX_HISTORICAL_EVIDENCE_PER_PATCH = 8

_SNAPSHOT_NUMBER_FIELDS = (
    "latest_close",
    "volume",
    "turnover",
    "return_20d",
    "return_60d",
    "return_250d",
    "annualised_volatility",
    "max_drawdown",
)


def _required_text(value: object, field: str, *, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchCaseValidationError(f"{field}必须是非空文本。")
    cleaned = value.strip()
    if len(cleaned) > limit:
        raise ResearchCaseValidationError(f"{field}超过{limit}个字符。")
    return cleaned


def _bounded_text(value: object, *, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit]


def _iso_date(value: object, field: str) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = _required_text(value, field, limit=10)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise ResearchCaseValidationError(f"{field}不是有效ISO日期。") from exc
    if parsed.isoformat() != text:
        raise ResearchCaseValidationError(f"{field}不是规范ISO日期。")
    return text


def _emitted_date(value: object) -> date:
    text = _required_text(value, "emitted_at", limit=50)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ResearchCaseValidationError("emitted_at不是有效ISO时间。") from exc
    if parsed.tzinfo is None:
        raise ResearchCaseValidationError("emitted_at必须包含时区。")
    return parsed.date()


def _finite_number(value: object, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ResearchCaseValidationError(f"snapshot.{field}必须是有限数字或null。")
    number = float(value)
    if not math.isfinite(number):
        raise ResearchCaseValidationError(f"snapshot.{field}必须是有限数字或null。")
    return round(number, 8)


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ResearchCaseValidationError(f"snapshot.{field}必须是正整数。")
    return value


def _identifier(prefix: str, *parts: str) -> str:
    material = "\x1f".join(parts).encode("utf-8")
    digest = hashlib.sha256(material).hexdigest()[:24]
    return f"{prefix}-{digest}"


def _payload_size(value: object) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )


def _normalise_snapshot(snapshot: object) -> dict[str, object]:
    if not isinstance(snapshot, Mapping):
        raise ResearchCaseValidationError("Historical Lens snapshot必须是对象。")
    requested_date = _iso_date(
        snapshot.get("requested_date"), "snapshot.requested_date"
    )
    effective_date = _iso_date(
        snapshot.get("effective_market_date"),
        "snapshot.effective_market_date",
    )
    if effective_date > requested_date:
        raise ResearchCaseValidationError("实际采用交易日不能晚于历史截止日。")

    clean: dict[str, object] = {
        "requested_date": requested_date,
        "effective_market_date": effective_date,
        "observations": _positive_int(snapshot.get("observations"), "observations"),
        "source": _required_text(snapshot.get("source"), "snapshot.source", limit=180),
        "adjustment": _required_text(
            snapshot.get("adjustment"), "snapshot.adjustment", limit=40
        ),
    }
    for field in _SNAPSHOT_NUMBER_FIELDS:
        clean[field] = _finite_number(snapshot.get(field), field)
    return clean


def _candidate_records(evidence_result: object) -> list[Mapping[str, object]]:
    if evidence_result is None:
        return []
    if not isinstance(evidence_result, Mapping):
        raise ResearchCaseValidationError("Historical Lens evidence_result必须是对象或null。")
    accepted = evidence_result.get("accepted")
    if not isinstance(accepted, list):
        raise ResearchCaseValidationError("evidence_result.accepted必须是数组。")
    return [item for item in accepted if isinstance(item, Mapping)]


def _normalise_official_evidence(
    case: Mapping[str, object],
    evidence_result: object,
    *,
    cutoff: str,
) -> tuple[list[dict[str, object]], int]:
    """Return bounded, re-filtered official evidence and rejection count."""
    if isinstance(evidence_result, Mapping) and "as_of_date" in evidence_result:
        result_cutoff = _iso_date(
            evidence_result.get("as_of_date"), "evidence_result.as_of_date"
        )
        if result_cutoff != cutoff:
            raise ResearchCaseValidationError(
                "evidence_result截止日与Historical Lens快照不一致。"
            )
    candidates = _candidate_records(evidence_result)
    accepted: list[tuple[str, dict[str, object]]] = []
    rejected_count = 0
    seen_ids: set[str] = set()

    for record in candidates:
        try:
            published = _iso_date(
                record.get("published_date"), "evidence.published_date"
            )
        except ResearchCaseValidationError:
            rejected_count += 1
            continue
        raw_source_url = record.get("source_url")
        source_url = (
            raw_source_url.strip()
            if isinstance(raw_source_url, str)
            and 0 < len(raw_source_url.strip()) <= 800
            else ""
        )
        title = _bounded_text(record.get("title"), limit=400)
        if (
            published > cutoff
            or not title
            or record.get("evidence_grade") != "A"
            or record.get("verification_status") != "verified"
            or not is_allowed_evidence_url(
                source_url,
                source_tier="official_disclosure",
                company=case["company"],
            )
        ):
            rejected_count += 1
            continue

        evidence_id = _identifier(
            "evidence-historical",
            str(case["case_id"]),
            source_url,
            published,
        )
        if evidence_id in seen_ids:
            continue
        seen_ids.add(evidence_id)
        item: dict[str, object] = {
            "evidence_id": evidence_id,
            "source_module": "historical_lens",
            "source_tier": "official_disclosure",
            "title": title,
            "source_url": source_url,
            "published_date": published,
            "review_status": "not_required",
            "basis": "Historical Lens按官方公开发布日期纳入；时间接近不代表因果。",
        }
        page_number = record.get("page_number")
        if (
            isinstance(page_number, int)
            and not isinstance(page_number, bool)
            and page_number > 0
        ):
            item["page_start"] = page_number
            item["page_end"] = page_number
        accepted.append((published, item))

    accepted.sort(key=lambda pair: (pair[0], str(pair[1]["title"])), reverse=True)

    existing_ids = {
        str(item["evidence_id"]) for item in case.get("evidence", [])
    }
    remaining_capacity = MAX_EVIDENCE - len(existing_ids)
    selected: list[dict[str, object]] = []
    considered_count = 0
    for _, item in accepted:
        considered_count += 1
        is_existing = str(item["evidence_id"]) in existing_ids
        if is_existing or remaining_capacity > 0:
            selected.append(item)
            if not is_existing:
                remaining_capacity -= 1
        else:
            rejected_count += 1
        if len(selected) >= MAX_HISTORICAL_EVIDENCE_PER_PATCH:
            break
    rejected_count += max(0, len(accepted) - considered_count)
    return selected, rejected_count


def _merge_ids(existing: object, incoming: list[str], *, limit: int) -> list[str]:
    result = (
        [item for item in existing if isinstance(item, str)]
        if isinstance(existing, list)
        else []
    )
    for identifier in incoming:
        if identifier not in result:
            result.append(identifier)
    if len(result) > limit:
        raise ResearchCaseCapacityError(
            "案件引用容量不足，不能安全写入Historical Lens结果。"
        )
    return result


def _build_payload(
    snapshot: Mapping[str, object],
    *,
    evidence_ids: list[str],
    rejected_evidence_count: int,
) -> dict[str, object]:
    payload = {
        "schema": "historical-lens-snapshot.v1",
        "cutoff_date": snapshot["requested_date"],
        "effective_market_date": snapshot["effective_market_date"],
        "market_state": {
            field: snapshot[field] for field in _SNAPSHOT_NUMBER_FIELDS
        },
        "observations": snapshot["observations"],
        "source": snapshot["source"],
        "adjustment": snapshot["adjustment"],
        "official_evidence_ids": evidence_ids,
        "official_evidence_count": len(evidence_ids),
        "rejected_evidence_count": rejected_evidence_count,
        "controls": {
            "publication_cutoff_enforced": True,
            "later_outcomes_included": False,
            "causal_claim_allowed": False,
        },
    }
    if _payload_size(payload) > HISTORICAL_ARTIFACT_PAYLOAD_BYTES:
        raise ResearchCaseCapacityError(
            "Historical Lens artifact.payload超过桥接层4KB限制。"
        )
    return payload


def build_historical_lens_case_patch(
    case: object,
    snapshot: object,
    evidence_result: object,
    *,
    patch_id: object,
    emitted_at: object,
) -> dict[str, Any]:
    """Build an applicable CasePatch from a point-in-time snapshot.

    ``evidence_result`` may be ``None`` when the official disclosure endpoint
    failed.  In that case the market artifact is retained, but the
    ``point_in_time`` question remains blocked with an explicit retry action.
    """
    validate_research_case(case)
    if not isinstance(case, Mapping):  # Static type narrowing.
        raise ResearchCaseValidationError("研究案件必须是对象。")
    clean_snapshot = _normalise_snapshot(snapshot)
    cutoff = str(clean_snapshot["requested_date"])
    if date.fromisoformat(cutoff) > _emitted_date(emitted_at):
        raise ResearchCaseValidationError("历史截止日不能晚于补丁生成日。")

    scope = case["scope"]
    if scope["mode"] == "historical":
        if cutoff != scope["as_of_date"]:
            raise ResearchCaseValidationError(
                "Historical Lens截止日与历史案件截止日不一致。"
            )
        if clean_snapshot["effective_market_date"] != scope["effective_market_date"]:
            raise ResearchCaseValidationError(
                "Historical Lens实际交易日与历史案件范围不一致。"
            )

    # ``patch_id`` remains in the public signature for compatibility with
    # existing callers, but it is only a bounded request label.  The applied
    # patch identifier below is content-addressed so retries cannot append the
    # same historical result under a fresh random ID.
    _required_text(patch_id, "patch_id", limit=80)
    clean_emitted_at = _required_text(emitted_at, "emitted_at", limit=50)
    evidence, rejected_count = _normalise_official_evidence(
        case,
        evidence_result,
        cutoff=cutoff,
    )
    evidence_ids = [str(item["evidence_id"]) for item in evidence]
    artifact_id = _identifier(
        "artifact-historical",
        str(case["case_id"]),
        cutoff,
    )
    payload = _build_payload(
        clean_snapshot,
        evidence_ids=evidence_ids,
        rejected_evidence_count=rejected_count,
    )
    patch_content = json.dumps(
        {
            "case_id": case["case_id"],
            "canonical_code": case["company"]["canonical_code"],
            "scope": {
                "mode": scope["mode"],
                "as_of_date": scope["as_of_date"],
            },
            "snapshot": clean_snapshot,
            "evidence": evidence,
            "payload": payload,
        },
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    clean_patch_id = _identifier("patch-historical", patch_content)

    has_official_evidence = bool(evidence_ids)
    if has_official_evidence:
        status = "answered"
        summary = (
            f"截至{cutoff}，按公开发布日期保留{len(evidence_ids)}条可核验官方证据；"
            f"行情快照采用{clean_snapshot['effective_market_date']}交易日的"
            f"{clean_snapshot['adjustment']}数据。时间接近只作为调查线索，不证明因果。"
        )
        question_next_action = (
            "将当时可见证据与财务、市场材料交叉核验，不得用后来结果倒推。"
        )
    else:
        status = "blocked"
        summary = (
            f"截至{cutoff}已形成市场快照，但没有取得通过来源、发布日期与验证状态"
            "校验的官方原文，不能形成历史时点结论。"
        )
        question_next_action = (
            "返回 Historical Lens 重试官方公告源或调整截止日；取得截止日前官方原文后再判断。"
        )

    prior_brief = case["case_brief"]
    prior_brief_evidence = prior_brief["evidence"]
    merged_artifact_ids = _merge_ids(
        prior_brief_evidence["artifact_ids"], [artifact_id], limit=25
    )
    merged_evidence_ids = _merge_ids(
        prior_brief_evidence["evidence_ids"], evidence_ids, limit=MAX_EVIDENCE
    )
    previous_summary = _bounded_text(
        prior_brief_evidence.get("summary"), limit=1_900
    )
    combined_summary = "；".join(
        item for item in (previous_summary, summary) if item
    )[:3_000]

    existing_primary = _bounded_text(
        prior_brief.get("primary_question"), limit=1_000
    )
    existing_next_action = prior_brief.get("next_action")
    preserve_next_action = (
        has_official_evidence
        and isinstance(existing_next_action, Mapping)
        and existing_next_action.get("module") is not None
    )
    next_action = (
        deepcopy(dict(existing_next_action))
        if preserve_next_action
        else {
            "module": (
                "historical_lens"
                if not has_official_evidence
                else "research_thesis"
            ),
            "action": (
                "补取截止日前官方原文"
                if not has_official_evidence
                else "把历史时点证据纳入研究判断"
            ),
            "reason": (
                "当前只有市场快照，缺少可验证的官方披露。"
                if not has_official_evidence
                else "截止日隔离已经完成，下一步需要与其他证据交叉核验。"
            ),
        }
    )

    patch: dict[str, Any] = {
        "patch_id": clean_patch_id,
        "case_id": case["case_id"],
        "base_revision": case["revision"],
        "canonical_code": case["company"]["canonical_code"],
        "mode": scope["mode"],
        "as_of_date": scope["as_of_date"],
        "emitted_at": clean_emitted_at,
        "source_module": "historical_lens",
        "artifact": {
            "artifact_id": artifact_id,
            "module": "historical_lens",
            "title": f"{case['company']['name']}｜截至{cutoff}的Historical Lens快照",
            "generated_at": clean_emitted_at,
            "payload": payload,
            "review_status": "not_required",
        },
        "evidence": evidence,
        "case_brief_update": {
            "primary_question": existing_primary
            or f"截至{cutoff}，当时已经公开了哪些可验证证据？",
            "evidence": {
                "summary": combined_summary,
                "artifact_ids": merged_artifact_ids,
                "evidence_ids": merged_evidence_ids,
            },
            "next_action": next_action,
        },
        "question_updates": {
            "point_in_time": {
                "status": status,
                "summary": summary,
                "next_action": question_next_action,
                "artifact_ids": [artifact_id],
                "evidence_ids": evidence_ids,
            }
        },
        "audit_message": (
            f"Historical Lens已按{cutoff}截止线写入；官方证据{len(evidence_ids)}条，"
            f"未通过准入{rejected_count}条；未写入任何后来结果。"
        ),
    }

    # Validate the complete atomic result, including URL tiers, date cut-off,
    # source-module consistency and all artifact/evidence references.
    apply_case_patch(case, patch)
    return patch
