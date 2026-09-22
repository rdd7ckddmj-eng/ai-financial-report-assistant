"""Translate one official-disclosure delta review into a ResearchCase patch.

The bridge is pure and UI-free.  It deliberately stores only a small set of
official announcement references.  It does not copy response bodies, PDFs,
HTML, dataframes or an upstream interpretation of whether news is positive or
negative.  ``attention`` remains a reading-priority label only.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
import hashlib
import json
from typing import Any

from src.research_case import (
    MAX_ARTIFACTS,
    MAX_EVIDENCE,
    MAX_UNKNOWNS,
    ResearchCaseCapacityError,
    ResearchCaseValidationError,
    apply_case_patch,
    is_allowed_evidence_url,
    validate_research_case,
)


EVIDENCE_DELTA_ARTIFACT_PAYLOAD_BYTES = 20_000
MAX_EVIDENCE_DELTA_EVIDENCE_PER_PATCH = 8
MAX_EVIDENCE_DELTA_INPUT_ITEMS = 100

_ATTENTION_ORDER = {"高": 0, "中": 1, "低": 2}
_CATEGORY_GROUPS = {
    "财务报告": "财务与业绩",
    "业绩动态": "财务与业绩",
    "经营动态": "经营事项",
    "分红与回购": "资本运作",
    "股权与资本": "资本运作",
    "公司治理": "治理与风险",
    "监管与风险": "治理与风险",
}


def _error(message: str) -> ResearchCaseValidationError:
    return ResearchCaseValidationError(message)


def _bounded_text(value: object, *, limit: int) -> str:
    """Return compact text without stringifying arbitrary caller objects."""
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
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = _required_text(value, field=field, limit=10)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise _error(f"{field}不是有效ISO日期。") from exc
    if parsed.isoformat() != text:
        raise _error(f"{field}必须使用YYYY-MM-DD格式。")
    return text


def _optional_iso_date(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    return _iso_date(value, field=field)


def _iso_datetime(value: object, *, field: str) -> tuple[str, datetime]:
    text = _required_text(value, field=field, limit=50)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _error(f"{field}不是有效ISO日期时间。") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _error(f"{field}必须包含时区。")
    return text, parsed


def _identifier(prefix: str, *parts: str) -> str:
    material = "\x1f".join(parts).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(material).hexdigest()[:24]}"


def _json_size(value: object) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )


def _normalise_window(
    case: Mapping[str, object],
    review: Mapping[str, object],
    *,
    emitted_date: date,
) -> dict[str, object]:
    raw_window = review.get("window")
    if not isinstance(raw_window, Mapping):
        raise _error("EvidenceDeltaReview.window必须是对象。")
    start_date = _iso_date(
        raw_window.get("start_date"), field="review.window.start_date"
    )
    end_date = _iso_date(
        raw_window.get("end_date"), field="review.window.end_date"
    )
    baseline_date = _optional_iso_date(
        raw_window.get("baseline_date"),
        field="review.window.baseline_date",
    )
    if start_date > end_date:
        raise _error("公告增量窗口开始日不能晚于结束日。")
    if (date.fromisoformat(end_date) - date.fromisoformat(start_date)).days >= 365:
        raise _error("公告增量窗口不能超过365天。")
    if end_date > emitted_date.isoformat():
        raise _error("公告增量窗口不能晚于补丁生成日。")
    if baseline_date is not None and baseline_date > end_date:
        raise _error("公告复核基准日不能晚于窗口结束日。")

    expected_baseline: str | None = None
    checked_at = case["tracking"].get("evidence_checked_at")
    if isinstance(checked_at, str):
        try:
            expected_baseline = datetime.fromisoformat(
                checked_at.replace("Z", "+00:00")
            ).date().isoformat()
        except ValueError as exc:  # The case contract normally catches this.
            raise _error("案件公告检查点不是有效时间。") from exc
    if baseline_date != expected_baseline:
        raise _error("公告增量窗口基准日与当前案件检查点不一致。")

    expected_mode = "首次基准" if baseline_date is None else "增量复核"
    mode = _bounded_text(raw_window.get("mode"), limit=20)
    if mode != expected_mode:
        raise _error("公告增量窗口模式与案件检查点不一致。")
    truncated = raw_window.get("truncated")
    if not isinstance(truncated, bool):
        raise _error("review.window.truncated必须是布尔值。")
    return {
        "start_date": start_date,
        "end_date": end_date,
        "baseline_date": baseline_date,
        "mode": mode,
        "truncated": truncated,
    }


def _normalise_items(
    case: Mapping[str, object],
    review: Mapping[str, object],
    *,
    window: Mapping[str, object],
    generated_on: str,
) -> tuple[list[dict[str, str]], int]:
    raw_items = review.get("items")
    if not isinstance(raw_items, (list, tuple)):
        raise _error("EvidenceDeltaReview.items必须是数组。")

    candidates: list[dict[str, str]] = []
    rejected_count = max(0, len(raw_items) - MAX_EVIDENCE_DELTA_INPUT_ITEMS)
    start_date = str(window["start_date"])
    end_date = str(window["end_date"])
    baseline_date = window["baseline_date"]
    for raw in raw_items[:MAX_EVIDENCE_DELTA_INPUT_ITEMS]:
        if not isinstance(raw, Mapping):
            rejected_count += 1
            continue
        title = _bounded_text(raw.get("title"), limit=300)
        raw_source_url = raw.get("source_url")
        source_url = (
            raw_source_url.strip()
            if isinstance(raw_source_url, str)
            and 0 < len(raw_source_url.strip()) <= 800
            else ""
        )
        try:
            published_date = _iso_date(
                raw.get("published_date"), field="review.items.published_date"
            )
        except ResearchCaseValidationError:
            rejected_count += 1
            continue
        if (
            not title
            or published_date < start_date
            or published_date > end_date
            or published_date > generated_on
            or not is_allowed_evidence_url(
                source_url,
                source_tier="official_disclosure",
                company=case["company"],
            )
        ):
            rejected_count += 1
            continue

        source_category = (
            _bounded_text(raw.get("source_category"), limit=40) or "其他公告"
        )
        evidence_group = _CATEGORY_GROUPS.get(source_category, "其他")
        attention = _bounded_text(raw.get("attention"), limit=4)
        if attention not in _ATTENTION_ORDER:
            attention = "低"

        # Derive the status again.  A caller cannot promote a same-day item to
        # "new" when the official feed lacks a reliable publication time.
        if baseline_date is None:
            delta_status = "首次基准"
        elif published_date > str(baseline_date):
            delta_status = "新增"
        else:
            delta_status = "同日待复核"
        candidates.append(
            {
                "title": title,
                "published_date": published_date,
                "source_url": source_url,
                "source_category": source_category,
                "evidence_group": evidence_group,
                "attention": attention,
                "delta_status": delta_status,
            }
        )

    candidates.sort(
        key=lambda item: (
            -date.fromisoformat(item["published_date"]).toordinal(),
            _ATTENTION_ORDER[item["attention"]],
            item["title"],
            item["source_url"],
        )
    )
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in candidates:
        key = (item["published_date"], item["source_url"])
        if key in seen:
            rejected_count += 1
            continue
        seen.add(key)
        result.append(item)
    return result, rejected_count


def _evidence_id(case: Mapping[str, object], item: Mapping[str, str]) -> str:
    return _identifier(
        "evidence-delta",
        str(case["case_id"]),
        item["published_date"],
        item["source_url"],
    )


def _select_items(
    case: Mapping[str, object],
    items: list[dict[str, str]],
) -> tuple[list[dict[str, str]], int]:
    existing_ids = {str(item["evidence_id"]) for item in case["evidence"]}
    remaining_capacity = MAX_EVIDENCE - len(existing_ids)
    selected: list[dict[str, str]] = []
    omitted = 0
    for item in items:
        evidence_id = _evidence_id(case, item)
        if len(selected) >= MAX_EVIDENCE_DELTA_EVIDENCE_PER_PATCH:
            omitted += 1
            continue
        if evidence_id in existing_ids:
            selected.append(item)
            continue
        if remaining_capacity <= 0:
            omitted += 1
            continue
        selected.append(item)
        remaining_capacity -= 1
    return selected, omitted


def _merge_ids(existing: object, incoming: list[str], *, limit: int) -> list[str]:
    current = (
        [item for item in existing if isinstance(item, str)]
        if isinstance(existing, list)
        else []
    )
    result = list(dict.fromkeys([*current, *incoming]))
    if len(result) > limit:
        raise ResearchCaseCapacityError("案件引用容量不足，不能安全写入公告增量。")
    return result


def _merge_unknowns(
    case: Mapping[str, object],
    *,
    window_key: str,
    blocked_summary: str | None,
) -> list[dict[str, str]] | None:
    unknown_id = _identifier(
        "unknown-evidence-delta", str(case["case_id"]), window_key
    )
    existing = [
        {"unknown_id": str(item["unknown_id"]), "summary": str(item["summary"])}
        for item in case["case_brief"]["unknowns"]
        if item["unknown_id"] != unknown_id
    ]
    if blocked_summary and len(existing) < MAX_UNKNOWNS:
        existing.append({"unknown_id": unknown_id, "summary": blocked_summary})
    if existing == case["case_brief"]["unknowns"]:
        return None
    return existing


def _build_payload(
    *,
    canonical_code: str,
    window: Mapping[str, object],
    generated_on: str,
    selected: list[dict[str, str]],
    valid_count: int,
    rejected_count: int,
    omitted_count: int,
    case: Mapping[str, object],
    item_limit_reached: bool,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": "evidence-delta-review.v1",
        "canonical_code": canonical_code,
        "window": dict(window),
        "generated_on": generated_on,
        "counts": {
            "valid_official": valid_count,
            "written_to_case": len(selected),
            "high_attention": sum(item["attention"] == "高" for item in selected),
            "same_day_pending": sum(
                item["delta_status"] == "同日待复核" for item in selected
            ),
            "rejected_or_duplicate": rejected_count,
            "omitted_by_case_limit": omitted_count,
        },
        "official_references": [
            {
                "evidence_id": _evidence_id(case, item),
                "source_category": item["source_category"],
                "evidence_group": item["evidence_group"],
                "attention": item["attention"],
                "delta_status": item["delta_status"],
            }
            for item in selected
        ],
        "controls": {
            "official_disclosure_domain_revalidated": True,
            "attention_is_directional_judgement": False,
            "same_day_publication_time_requires_review": True,
            "binary_or_full_response_stored": False,
            "upstream_item_limit_reached": item_limit_reached,
        },
    }
    if _json_size(payload) > EVIDENCE_DELTA_ARTIFACT_PAYLOAD_BYTES:
        raise ResearchCaseCapacityError("公告增量artifact.payload超过20KB限制。")
    return payload


def build_evidence_delta_research_case_patch(
    case: object,
    review: object,
    *,
    emitted_at: object,
) -> dict[str, Any]:
    """Build and preflight a deterministic ``evidence_delta`` CasePatch.

    Only current-scope cases are accepted.  Historical cases must use
    Historical Lens so a later announcement can never leak across a cut-off.
    """
    validate_research_case(case)
    if not isinstance(case, Mapping):  # Static type narrowing after validation.
        raise _error("研究案件必须是对象。")
    if case["scope"]["mode"] != "current":
        raise _error("公告增量只能写入当前案件；历史案件请使用Historical Lens。")
    if not isinstance(review, Mapping):
        raise _error("EvidenceDeltaReview必须是对象。")
    clean_emitted_at, emitted = _iso_datetime(emitted_at, field="emitted_at")

    review_company = review.get("company")
    if not isinstance(review_company, Mapping):
        raise _error("EvidenceDeltaReview缺少公司身份。")
    canonical_code = _bounded_text(
        review_company.get("canonical_code"), limit=16
    ).upper()
    if canonical_code != case["company"]["canonical_code"]:
        raise _error("公告增量与研究案件公司不匹配。")

    generated_on = _iso_date(
        review.get("generated_on"), field="review.generated_on"
    )
    if generated_on > emitted.date().isoformat():
        raise _error("公告增量生成日不能晚于补丁生成日。")
    window = _normalise_window(case, review, emitted_date=emitted.date())
    if str(window["end_date"]) > generated_on:
        raise _error("公告增量窗口结束日不能晚于复核生成日。")

    normalised, rejected_count = _normalise_items(
        case,
        review,
        window=window,
        generated_on=generated_on,
    )
    selected, omitted_count = _select_items(case, normalised)
    item_limit_reached = review.get("item_limit_reached")
    if not isinstance(item_limit_reached, bool):
        item_limit_reached = (
            len(review.get("items", [])) > MAX_EVIDENCE_DELTA_INPUT_ITEMS
        )
    evidence: list[dict[str, object]] = []
    for item in selected:
        evidence.append(
            {
                "evidence_id": _evidence_id(case, item),
                "source_module": "evidence_delta",
                "source_tier": "official_disclosure",
                "title": item["title"],
                "source_url": item["source_url"],
                "published_date": item["published_date"],
                "review_status": "not_required",
                "basis": (
                    f"类别：{item['source_category']}；证据组：{item['evidence_group']}；"
                    f"增量状态：{item['delta_status']}；关注程度：{item['attention']}。"
                    "关注程度仅表示阅读优先级，不代表利好、利空或价格方向。"
                ),
            }
        )
    evidence_ids = [str(item["evidence_id"]) for item in evidence]

    window_key = (
        f"{window['start_date']}:{window['end_date']}:"
        f"{window['baseline_date'] or 'none'}"
    )
    digest_material = {
        "canonical_code": canonical_code,
        "window": window,
        "generated_on": generated_on,
        "items": normalised,
        "rejected_count": rejected_count,
        "omitted_count": omitted_count,
        "selected_evidence_ids": evidence_ids,
        "item_limit_reached": item_limit_reached,
    }
    review_digest = hashlib.sha256(
        json.dumps(
            digest_material,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:24]
    patch_id = f"patch-evidence-delta-{review_digest}"
    artifact_id = _identifier(
        "artifact-evidence-delta", str(case["case_id"]), window_key
    )
    existing_artifact_ids = {
        str(item["artifact_id"]) for item in case["artifacts"]
    }
    if artifact_id not in existing_artifact_ids and len(existing_artifact_ids) >= MAX_ARTIFACTS:
        raise ResearchCaseCapacityError("案件artifact容量已满，不能写入公告增量。")

    payload = _build_payload(
        canonical_code=canonical_code,
        window=window,
        generated_on=generated_on,
        selected=selected,
        valid_count=len(normalised),
        rejected_count=rejected_count,
        omitted_count=omitted_count,
        case=case,
        item_limit_reached=item_limit_reached,
    )

    prior_brief_evidence = case["case_brief"]["evidence"]
    brief_artifact_ids = _merge_ids(
        prior_brief_evidence["artifact_ids"], [artifact_id], limit=MAX_ARTIFACTS
    )
    brief_evidence_ids = _merge_ids(
        prior_brief_evidence["evidence_ids"], evidence_ids, limit=MAX_EVIDENCE
    )
    recent_question = case["questions"]["recent_events"]
    recent_artifact_ids = _merge_ids(
        recent_question["artifact_ids"], [artifact_id], limit=MAX_ARTIFACTS
    )
    recent_evidence_ids = _merge_ids(
        recent_question["evidence_ids"], evidence_ids, limit=MAX_EVIDENCE
    )

    if evidence:
        recent_status = "in_progress"
        recent_summary = (
            f"{window['start_date']}至{window['end_date']}保留"
            f"{len(evidence)}条通过官方域名复核的公告引用；"
            f"其中{sum(item['attention'] == '高' for item in selected)}条为高关注、"
            f"{sum(item['delta_status'] == '同日待复核' for item in selected)}条需同日复核。"
            "关注程度只决定阅读优先级，不代表方向判断。"
        )
        recent_next_action = "打开公告原文，核验事实、口径与对案件判断的实际影响。"
        primary_question = f"公告《{selected[0]['title']}》及同窗口变动需要核验什么？"
        next_action = {
            "module": "evidence_delta",
            "action": "逐条阅读本轮官方公告原文",
            "reason": "标题分类与关注程度不能替代原文核验，也不能直接形成方向判断。",
        }
        blocked_unknown = None
        evidence_summary = (
            f"本轮新增{len(evidence)}条官方公告引用；类别、关注程度与同日待复核状态已保留，"
            "但尚未把标题分类解释成研究结论。"
        )
    else:
        recent_status = "blocked"
        recent_summary = (
            f"{window['start_date']}至{window['end_date']}未写入通过来源与日期校验的"
            "官方公告引用；这不能证明期间没有公告。"
        )
        recent_next_action = "重新检查官方公告源，区分确无公告、来源失败与案件容量不足。"
        primary_question = "该窗口是否确无官方公告，还是来源或案件容量仍待处理？"
        next_action = {
            "module": "evidence_delta",
            "action": "重新执行官方公告增量复核",
            "reason": "没有可追溯引用时，不得将空结果解释为没有发生事项。",
        }
        blocked_unknown = (
            f"待核验：{window['start_date']}至{window['end_date']}未取得可写入案件的"
            "官方公告引用，需区分确无公告、来源失败与容量限制。"
        )
        evidence_summary = "本轮只保存了空结果控制记录，没有伪造或补写任何公告证据。"

    if omitted_count:
        recent_next_action += f" 另有{omitted_count}条因单次写入或案件容量限制未保存。"
    prior_summary = _bounded_text(
        prior_brief_evidence.get("summary"), limit=1_700
    )
    if prior_summary:
        evidence_summary = f"{evidence_summary} 既有案件摘要：{prior_summary}"
    unknowns = _merge_unknowns(
        case,
        window_key=window_key,
        blocked_summary=blocked_unknown,
    )

    patch: dict[str, Any] = {
        "patch_id": patch_id,
        "case_id": case["case_id"],
        "base_revision": case["revision"],
        "canonical_code": canonical_code,
        "mode": case["scope"]["mode"],
        "as_of_date": case["scope"]["as_of_date"],
        "emitted_at": clean_emitted_at,
        "source_module": "evidence_delta",
        "artifact": {
            "artifact_id": artifact_id,
            "module": "evidence_delta",
            "title": f"{case['company']['name']}｜官方公告增量复核",
            "generated_at": clean_emitted_at,
            "payload": payload,
            "review_status": "not_required",
        },
        "evidence": evidence,
        "case_brief_update": {
            "primary_question": primary_question,
            "evidence": {
                "summary": evidence_summary,
                "artifact_ids": brief_artifact_ids,
                "evidence_ids": brief_evidence_ids,
            },
            "next_action": next_action,
        },
        "question_updates": {
            "recent_events": {
                "status": recent_status,
                "summary": recent_summary,
                "next_action": recent_next_action,
                "artifact_ids": recent_artifact_ids,
                "evidence_ids": recent_evidence_ids,
            }
        },
        "audit_message": (
            "已写入官方公告增量的紧凑引用；关注程度仅用于阅读排序，"
            "未保存二进制或生成方向判断。"
        ),
    }
    if unknowns is not None:
        patch["case_brief_update"]["unknowns"] = unknowns
    if evidence:
        # The next query includes this calendar day again.  Using emitted_at
        # here could skip a day when a saved review is written after midnight.
        patch["tracking"] = {
            "evidence_checked_at": f"{window['end_date']}T00:00:00+00:00"
        }

    # Preflight the exact patch against the canonical reducer.  This catches
    # dangling references, capacity overflow and any future contract drift.
    apply_case_patch(case, patch)
    return patch


# Short alias for callers that follow the Historical Lens bridge naming style.
build_evidence_delta_case_patch = build_evidence_delta_research_case_patch
