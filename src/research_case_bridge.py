"""Translate one comprehensive-research brief into a compact CasePatch.

This bridge is deliberately pure and UI-free.  It copies only bounded text,
source identifiers and validated public-source citations from the brief.  It
never stores the full brief, tables, charts, PDFs or arbitrary Python objects.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
import hashlib
import json
import math
from typing import Any

from src.research_case import (
    MAX_UNKNOWNS,
    ResearchCaseCapacityError,
    ResearchCaseValidationError,
    apply_case_patch,
    is_allowed_evidence_url,
    validate_research_case,
)


COMPREHENSIVE_ARTIFACT_PAYLOAD_BYTES = 4_000
MAX_BRIDGE_UNKNOWNS = 6

_LANE_KEYS = {
    "identity",
    "market",
    "disclosures",
    "annual_report",
    "financial_history",
    "point_in_time",
    "historical_lens",
}
_LANE_STATUSES = {"verified", "partial", "unavailable"}
_TIER_CANDIDATES = (
    "official_disclosure",
    "official_company",
    "public_market_data",
)
_ACTION_MODULES = {
    "company": "company_research",
    "company_research": "company_research",
    "comprehensive": "comprehensive_research",
    "comprehensive_research": "comprehensive_research",
    "market": "market_activity",
    "anomaly": "market_activity",
    "market_activity": "market_activity",
    "financial_snapshot": "financial_snapshot",
    "annual": "annual_report",
    "annual_report": "annual_report",
    "financial_trend": "financial_trend",
    "historical": "historical_lens",
    "historical_lens": "historical_lens",
    "evidence_delta": "evidence_delta",
    "thesis": "research_thesis",
    "research_thesis": "research_thesis",
}


def _compact_text(value: object, *, limit: int) -> str:
    """Return bounded scalar text without invoking arbitrary ``__str__``."""
    if not isinstance(value, str):
        return ""
    return " ".join(value.split()).strip()[:limit]


def _required_text(value: object, *, field: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchCaseValidationError(f"{field}必须是非空文本。")
    cleaned = value.strip()
    if len(cleaned) > limit:
        raise ResearchCaseValidationError(f"{field}超过{limit}个字符。")
    return cleaned


def _iso_date(value: object) -> str | None:
    text = _compact_text(value, limit=10)
    if not text:
        return None
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        return None
    return parsed.isoformat() if parsed.isoformat() == text else None


def _finite_ratio(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return round(min(max(number, 0.0), 1.0), 4)


def _identifier(prefix: str, *parts: object) -> str:
    material = "\x1f".join(
        part if isinstance(part, str) else ""
        for part in parts
    ).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(material).hexdigest()[:24]}"


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


def _source_tier(
    source_url: str,
    *,
    company: Mapping[str, object],
) -> str | None:
    for tier in _TIER_CANDIDATES:
        if is_allowed_evidence_url(
            source_url,
            source_tier=tier,
            company=company,
        ):
            return tier
    return None


def _normalise_lanes(
    brief: Mapping[str, object],
    *,
    case: Mapping[str, object],
) -> dict[str, dict[str, object]]:
    raw_lanes = brief.get("evidence_lanes")
    if not isinstance(raw_lanes, (list, tuple)):
        return {}

    cutoff = case["scope"]["as_of_date"]
    historical = case["scope"]["mode"] == "historical"
    lanes: dict[str, dict[str, object]] = {}
    # A valid comprehensive brief contains five lanes.  The small allowance
    # supports a future explicit Historical Lens lane without accepting an
    # unbounded caller-owned collection.
    for raw_lane in raw_lanes[:8]:
        if not isinstance(raw_lane, Mapping):
            continue
        key = _compact_text(raw_lane.get("key"), limit=40)
        if key not in _LANE_KEYS or key in lanes:
            continue
        status = _compact_text(raw_lane.get("status"), limit=20)
        if status not in _LANE_STATUSES:
            status = "unavailable"
        as_of_date = _iso_date(raw_lane.get("as_of_date"))
        raw_url = _compact_text(raw_lane.get("source_url"), limit=800)
        tier = _source_tier(raw_url, company=case["company"]) if raw_url else None

        summary = _compact_text(raw_lane.get("summary"), limit=600)
        limitation = _compact_text(raw_lane.get("limitation"), limit=500)
        if raw_url and tier is None:
            # Never preserve or cite a URL merely because the upstream brief
            # labelled the lane as verified.
            status = "partial" if status == "verified" else status
            limitation = "来源链接未通过案件来源白名单校验。"
        if historical and (as_of_date is None or as_of_date > str(cutoff)):
            status = "unavailable"
            raw_url = ""
            tier = None
            summary = "该证据没有完成案件截止日隔离，未写入历史案件。"
            limitation = "请使用 Historical Lens 按截止日期重新核验。"

        lanes[key] = {
            "key": key,
            "label": _compact_text(raw_lane.get("label"), limit=120) or key,
            "status": status,
            "summary": summary or "本次没有形成可保存的摘要。",
            "source": _compact_text(raw_lane.get("source"), limit=180),
            "as_of_date": as_of_date,
            "source_url": raw_url if tier else "",
            "source_tier": tier,
            "limitation": limitation,
        }
    return lanes


def _build_evidence(
    lanes: Mapping[str, Mapping[str, object]],
    *,
    case: Mapping[str, object],
) -> tuple[list[dict[str, object]], dict[str, list[str]]]:
    evidence: list[dict[str, object]] = []
    ids_by_lane: dict[str, list[str]] = {}
    for key, lane in lanes.items():
        source_url = lane.get("source_url")
        source_tier = lane.get("source_tier")
        published_date = lane.get("as_of_date")
        if not (
            isinstance(source_url, str)
            and source_url
            and isinstance(source_tier, str)
            and isinstance(published_date, str)
            and is_allowed_evidence_url(
                source_url,
                source_tier=source_tier,
                company=case["company"],
            )
        ):
            ids_by_lane[key] = []
            continue
        evidence_id = _identifier(
            "ev-comprehensive",
            str(case["company"]["canonical_code"]),
            key,
            source_url,
            published_date,
        )
        item: dict[str, object] = {
            "evidence_id": evidence_id,
            "source_module": "comprehensive_research",
            "source_tier": source_tier,
            "title": _compact_text(
                f"{lane.get('label', key)}｜{lane.get('source', '')}",
                limit=400,
            ),
            "source_url": source_url,
            "published_date": published_date,
            # A comprehensive lane summary is generated by the research
            # coordinator from upstream data.  A valid URL and a "verified"
            # lane status establish provenance/availability only; they do not
            # prove that this compact summary is verbatim official-source text
            # or that a human has confirmed it.  Keep the source record for
            # traceability without promoting it into the workpaper fact index.
            "review_status": "not_required",
        }
        excerpt = _compact_text(lane.get("summary"), limit=400)
        basis = _compact_text(lane.get("limitation"), limit=500)
        if excerpt:
            item["excerpt"] = excerpt
        item["basis"] = _compact_text(
            "程序根据上游公开数据生成的来源摘要，不是官方原文摘录，"
            "也未被自动升级为已确认事实。"
            + (f" {basis}" if basis else ""),
            limit=500,
        )
        evidence.append(item)
        ids_by_lane[key] = [evidence_id]
    return evidence, ids_by_lane


def _lane_question_update(
    lane: Mapping[str, object] | None,
    *,
    artifact_id: str,
    evidence_ids: list[str],
    blocked_summary: str,
    next_action: str,
) -> dict[str, object]:
    lane_status = lane.get("status") if lane else "unavailable"
    if lane_status == "verified":
        status = "answered"
        action = ""
    elif lane_status == "partial":
        status = "in_progress"
        action = next_action
    else:
        status = "blocked"
        action = next_action
    summary = _compact_text(lane.get("summary"), limit=900) if lane else ""
    return {
        "status": status,
        "summary": summary or blocked_summary,
        "next_action": action,
        "artifact_ids": [artifact_id],
        "evidence_ids": list(evidence_ids),
    }


def _historical_question_update(
    lanes: Mapping[str, Mapping[str, object]],
    *,
    case: Mapping[str, object],
    artifact_id: str,
    ids_by_lane: Mapping[str, list[str]],
) -> dict[str, object]:
    lane = lanes.get("historical_lens") or lanes.get("point_in_time")
    lane_key = str(lane.get("key")) if lane else ""
    evidence_ids = list(ids_by_lane.get(lane_key, []))
    is_cutoff_evidence = (
        case["scope"]["mode"] == "historical"
        and lane is not None
        and lane.get("status") in {"verified", "partial"}
        and bool(evidence_ids)
        and isinstance(lane.get("as_of_date"), str)
        and lane["as_of_date"] <= case["scope"]["as_of_date"]
    )
    if not is_cutoff_evidence:
        return {
            "status": "blocked",
            "summary": (
                "本次综合研究没有提供经历史截止日隔离并可追溯的证据，"
                "不能用后来信息解释当时。"
            ),
            "next_action": (
                "进入 Historical Lens，按案件截止日重新核验当时可得信息。"
            ),
            "artifact_ids": [artifact_id],
            "evidence_ids": [],
        }
    return {
        "status": "answered" if lane["status"] == "verified" else "in_progress",
        "summary": _compact_text(lane.get("summary"), limit=900),
        "next_action": (
            "" if lane["status"] == "verified" else "进入 Historical Lens 补齐截止日证据。"
        ),
        "artifact_ids": [artifact_id],
        "evidence_ids": evidence_ids,
    }


def _first_next_action(
    brief: Mapping[str, object],
) -> tuple[str, str, str]:
    raw_actions = brief.get("actions")
    if isinstance(raw_actions, (list, tuple)):
        candidates: list[tuple[int, str, str, str]] = []
        for raw in raw_actions[:10]:
            if not isinstance(raw, Mapping):
                continue
            page = _compact_text(raw.get("page"), limit=60)
            module = _ACTION_MODULES.get(page)
            action = _compact_text(raw.get("label"), limit=1_000)
            reason = _compact_text(raw.get("reason"), limit=2_000)
            priority = raw.get("priority")
            if (
                module
                and action
                and reason
                and isinstance(priority, int)
                and not isinstance(priority, bool)
            ):
                candidates.append((priority, module, action, reason))
        if candidates:
            _, module, action, reason = sorted(candidates)[0]
            return module, action, reason
    return (
        "research_thesis",
        "记录并复核当前研究判断",
        "将本次摘要与后续公开证据变化进行对照。",
    )


def _dedupe_key(value: str) -> str:
    return " ".join(value.casefold().split())


def _build_unknowns(
    case: Mapping[str, object],
    brief: Mapping[str, object],
    lanes: Mapping[str, Mapping[str, object]],
) -> list[dict[str, str]]:
    """Return a complete bounded unknown list without asserting absence.

    Existing human-entered unknowns are retained.  The bridge adds at most six
    deterministic gaps from partial/unavailable lanes and explicit brief
    limitations.  Every generated sentence is framed as work still requiring
    evidence, rather than turning an upstream hypothesis into a fact.
    """
    existing = case["case_brief"]["unknowns"]
    result = [
        {
            "unknown_id": str(item["unknown_id"]),
            "summary": str(item["summary"]),
        }
        for item in existing
    ]
    seen_ids = {item["unknown_id"] for item in result}
    seen_content = {_dedupe_key(item["summary"]) for item in result}
    candidate_content: set[str] = set(seen_content)
    generated = 0
    canonical_code = str(case["company"]["canonical_code"])

    def add_unknown(*, origin: str, content: str, summary: str) -> None:
        nonlocal generated
        core_key = _dedupe_key(content)
        summary_key = _dedupe_key(summary)
        if (
            not core_key
            or core_key in candidate_content
            or summary_key in seen_content
            or generated >= MAX_BRIDGE_UNKNOWNS
            or len(result) >= MAX_UNKNOWNS
        ):
            return
        unknown_id = _identifier(
            "unknown-comprehensive",
            canonical_code,
            origin,
            core_key,
        )
        if unknown_id in seen_ids:
            return
        result.append(
            {
                "unknown_id": unknown_id,
                "summary": _compact_text(summary, limit=1_800),
            }
        )
        seen_ids.add(unknown_id)
        seen_content.add(summary_key)
        candidate_content.add(core_key)
        generated += 1

    for key, lane in lanes.items():
        status = lane.get("status")
        if status not in {"partial", "unavailable"}:
            continue
        label = _compact_text(lane.get("label"), limit=120) or key
        content = _compact_text(lane.get("limitation"), limit=500)
        if not content:
            content = _compact_text(lane.get("summary"), limit=600)
        if not content:
            continue
        prefix = "待核验" if status == "partial" else "待补充"
        add_unknown(
            origin=f"lane:{key}",
            content=content,
            summary=f"{prefix}：{label}。{content}",
        )

    raw_limitations = brief.get("limitations")
    if isinstance(raw_limitations, (list, tuple)):
        for raw_limitation in raw_limitations[:12]:
            content = _compact_text(raw_limitation, limit=700)
            if not content:
                continue
            add_unknown(
                origin="limitation",
                content=content,
                summary=f"需人工覆盖检查：{content}",
            )

    if generated == 0 and len(result) < MAX_UNKNOWNS:
        fallback = (
            "尚未完成未知项登记；需人工覆盖检查是否仍有未披露、"
            "未解析或未核验的信息。"
        )
        add_unknown(
            origin="fallback",
            content=fallback,
            summary=fallback,
        )
    return result


def _build_artifact_payload(
    brief: Mapping[str, object],
    *,
    canonical_code: str,
    question_updates: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    conclusion = brief.get("conclusion")
    conclusion_map = conclusion if isinstance(conclusion, Mapping) else {}
    payload: dict[str, object] = {
        "schema": "comprehensive-summary.v1",
        "company_id": canonical_code,
        "generated_on": _iso_date(brief.get("generated_on")),
        "coverage": {
            "ratio": _finite_ratio(brief.get("coverage_ratio")),
            "label": _compact_text(brief.get("coverage_label"), limit=80),
        },
        "conclusion": {
            "summary": _compact_text(conclusion_map.get("headline"), limit=120),
            "next_question": _compact_text(
                conclusion_map.get("next_question"), limit=160
            ),
            "source_id": _compact_text(
                conclusion_map.get("primary_key"), limit=80
            ),
        },
        "questions": {
            key: {
                "status": update["status"],
                "summary": _compact_text(update.get("summary"), limit=80),
                "source_ids": [
                    *list(update.get("artifact_ids", [])),
                    *list(update.get("evidence_ids", [])),
                ],
            }
            for key, update in question_updates.items()
        },
    }
    size = _payload_size(payload)
    if size > COMPREHENSIVE_ARTIFACT_PAYLOAD_BYTES:
        raise ResearchCaseCapacityError(
            "综合研究摘要artifact.payload超过桥接层4KB限制。"
        )
    return payload


def build_comprehensive_research_case_patch(
    case: object,
    brief: object,
    *,
    patch_id: object,
    emitted_at: object,
) -> dict[str, Any]:
    """Build and validate one compact comprehensive-research CasePatch.

    ``apply_case_patch`` is called on a copy before return, so callers never
    receive a patch containing an invalid source tier, URL or dangling
    artifact/evidence reference.
    """
    validate_research_case(case)
    if not isinstance(case, Mapping):  # Kept for static type narrowing.
        raise ResearchCaseValidationError("研究案件必须是对象。")
    if not isinstance(brief, Mapping):
        raise ResearchCaseValidationError("综合研究brief必须是对象。")

    brief_company = brief.get("company")
    if not isinstance(brief_company, Mapping):
        raise ResearchCaseValidationError("综合研究brief缺少公司身份。")
    canonical_code = _compact_text(
        brief_company.get("canonical_code"), limit=16
    ).upper()
    if canonical_code != case["company"]["canonical_code"]:
        raise ResearchCaseValidationError("综合研究brief与案件公司不匹配。")

    clean_patch_id = _required_text(patch_id, field="patch_id", limit=80)
    clean_emitted_at = _required_text(
        emitted_at,
        field="emitted_at",
        limit=50,
    )

    lanes = _normalise_lanes(brief, case=case)
    evidence, ids_by_lane = _build_evidence(lanes, case=case)
    artifact_id = _identifier(
        "artifact-comprehensive",
        str(case["case_id"]),
    )

    question_updates: dict[str, dict[str, object]] = {
        "recent_events": _lane_question_update(
            lanes.get("disclosures"),
            artifact_id=artifact_id,
            evidence_ids=list(ids_by_lane.get("disclosures", [])),
            blocked_summary="本次没有形成可追溯的官方动态摘要。",
            next_action="进入公司研究页，补充并核验官方公告。",
        ),
        "market_change": _lane_question_update(
            lanes.get("market"),
            artifact_id=artifact_id,
            evidence_ids=list(ids_by_lane.get("market", [])),
            blocked_summary="本次没有形成可复核的市场变化摘要。",
            next_action="进入市场表现页，重新获取并核验行情证据。",
        ),
        "financial_quality": _lane_question_update(
            lanes.get("financial_history"),
            artifact_id=artifact_id,
            evidence_ids=[
                *list(ids_by_lane.get("financial_history", [])),
                *list(ids_by_lane.get("annual_report", [])),
            ],
            blocked_summary="本次没有形成可复核的财务质量摘要。",
            next_action="进入年报与证据分析，补充页码和财务口径。",
        ),
    }
    question_updates["point_in_time"] = _historical_question_update(
        lanes,
        case=case,
        artifact_id=artifact_id,
        ids_by_lane=ids_by_lane,
    )

    conclusion = brief.get("conclusion")
    conclusion_map = conclusion if isinstance(conclusion, Mapping) else {}
    headline = _compact_text(conclusion_map.get("headline"), limit=500)
    explanation = _compact_text(
        conclusion_map.get("explanation"), limit=700
    )
    next_question = _compact_text(
        conclusion_map.get("next_question"), limit=1_000
    )
    coverage = _finite_ratio(brief.get("coverage_ratio"))
    judgement_status = "blocked"
    if headline:
        judgement_status = (
            "answered"
            if coverage is not None and coverage >= 0.5
            else "in_progress"
        )
    question_updates["research_judgement"] = {
        "status": judgement_status,
        "summary": " ".join(item for item in (headline, explanation) if item)
        or "本次没有形成可保存的研究判断。",
        "next_action": "" if judgement_status == "answered" else (
            next_question or "补齐缺失证据后重新生成综合研究。"
        ),
        "artifact_ids": [artifact_id],
        "evidence_ids": [item["evidence_id"] for item in evidence],
    }
    unknowns = _build_unknowns(case, brief, lanes)

    payload = _build_artifact_payload(
        brief,
        canonical_code=canonical_code,
        question_updates=question_updates,
    )
    point_in_time_blocked = (
        question_updates["point_in_time"]["status"] == "blocked"
    )
    if point_in_time_blocked:
        next_module, next_action, next_reason = (
            "historical_lens",
            "按案件截止日核验当时可得信息",
            "综合研究摘要没有提供经截止日隔离的历史证据。",
        )
    else:
        next_module, next_action, next_reason = _first_next_action(brief)

    evidence_summary = _compact_text(
        conclusion_map.get("evidence_summary"), limit=2_000
    ) or _compact_text(brief.get("coverage_label"), limit=2_000)
    if not evidence_summary:
        evidence_summary = "本次综合研究已形成紧凑摘要，引用见五个问题通道。"

    patch: dict[str, Any] = {
        "patch_id": clean_patch_id,
        "case_id": case["case_id"],
        "base_revision": case["revision"],
        "canonical_code": canonical_code,
        "mode": case["scope"]["mode"],
        "as_of_date": case["scope"]["as_of_date"],
        "emitted_at": clean_emitted_at,
        "source_module": "comprehensive_research",
        "artifact": {
            "artifact_id": artifact_id,
            "module": "comprehensive_research",
            "title": f"{case['company']['name']}｜综合研究紧凑摘要",
            "generated_at": clean_emitted_at,
            "payload": payload,
            "review_status": "not_required",
        },
        "evidence": evidence,
        "case_brief_update": {
            "primary_question": next_question or headline or "下一步应优先核验哪条证据？",
            "evidence": {
                "summary": evidence_summary,
                "artifact_ids": [artifact_id],
                "evidence_ids": [item["evidence_id"] for item in evidence],
            },
            # Deliberately do not write ``contradictions`` here.  An empty
            # upstream collection is not evidence that no contradiction exists.
            "unknowns": unknowns,
            "next_action": {
                "module": next_module,
                "action": next_action,
                "reason": next_reason,
            },
        },
        "question_updates": question_updates,
        "audit_message": "已写入综合研究紧凑摘要；未保存完整brief或大对象。",
    }

    # Structural validation here is intentional: the bridge must never hand
    # the UI a patch that fails source-tier, URL, cutoff or reference checks.
    apply_case_patch(case, patch)
    return patch
