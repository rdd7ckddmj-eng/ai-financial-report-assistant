"""Pure, explicit migration from the legacy browser research state v3."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from typing import Any

from src.research_case import (
    HYPOTHESIS_STATUSES,
    MAX_AUDIT_LOG,
    MAX_HYPOTHESES,
    MAX_MIGRATION_IDS,
    ResearchCaseCapacityError,
    ResearchCaseValidationError,
    calculate_readiness,
    new_research_case,
    normalise_company_identity,
    validate_research_case,
)


LEGACY_STORAGE_VERSION = 3


def _clean_text(value: object, *, limit: int, required: bool = False) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split()).strip()
    if required and not cleaned:
        return None
    return cleaned[:limit]


def _is_iso_datetime(value: object) -> bool:
    if not isinstance(value, str) or "T" not in value:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _normalise_checkpoint(
    value: object,
    *,
    canonical_code: str,
) -> str | None:
    if not isinstance(value, list):
        return None
    for raw in value:
        if not isinstance(raw, Mapping):
            continue
        checked_at = raw.get("evidence_checked_at")
        if (
            raw.get("canonical_code") == canonical_code
            and _is_iso_datetime(checked_at)
        ):
            return str(checked_at)
    return None


def _normalise_legacy_hypothesis(
    value: object,
    *,
    canonical_code: str,
) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    if value.get("canonical_code") != canonical_code:
        return None
    hypothesis_id = _clean_text(value.get("thesis_id"), limit=80, required=True)
    statement = _clean_text(value.get("hypothesis"), limit=1_000, required=True)
    updated_at = value.get("updated_at")
    status = value.get("status")
    if (
        hypothesis_id is None
        or statement is None
        or status not in HYPOTHESIS_STATUSES
        or not _is_iso_datetime(updated_at)
    ):
        return None
    result: dict[str, Any] = {
        "hypothesis_id": hypothesis_id,
        "statement": statement,
        "status": str(status),
        "updated_at": str(updated_at),
        "source_module": "research_thesis",
        # Legacy thesis statuses were selected by a person, not inferred by AI.
        "review_status": "confirmed",
    }
    for old_field, new_field, limit in (
        ("topic", "topic", 80),
        ("confirmation_criteria", "confirmation_criteria", 1_000),
        ("invalidation_criteria", "invalidation_criteria", 1_000),
        ("review_note", "review_note", 1_000),
    ):
        cleaned = _clean_text(value.get(old_field), limit=limit)
        if cleaned:
            result[new_field] = cleaned
    created_at = value.get("created_at")
    if _is_iso_datetime(created_at):
        result["created_at"] = str(created_at)
    return result


def _normalise_hypotheses(
    value: object,
    *,
    canonical_code: str,
) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(value, list):
        return [], 0
    by_id: dict[str, dict[str, Any]] = {}
    invalid_matching = 0
    for raw in value:
        if not isinstance(raw, Mapping) or raw.get("canonical_code") != canonical_code:
            continue
        hypothesis = _normalise_legacy_hypothesis(
            raw,
            canonical_code=canonical_code,
        )
        if hypothesis is None:
            invalid_matching += 1
            continue
        by_id.setdefault(hypothesis["hypothesis_id"], hypothesis)
    # Sorting makes the migration hash independent from legacy UI list order.
    return [by_id[key] for key in sorted(by_id)], invalid_matching


def _migration_id(
    *,
    canonical_code: str,
    valid_v3: bool,
    checkpoint: str | None,
    hypotheses: list[dict[str, Any]],
) -> str:
    normalised = {
        "source": "browser_research_state.v3",
        "target": canonical_code,
        "valid_v3": valid_v3,
        "checkpoint": checkpoint,
        "hypotheses": hypotheses,
    }
    encoded = json.dumps(
        normalised,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def migrate_legacy_v3_case(
    legacy_state: object,
    *,
    company: object,
    case_id: object,
    migrated_at: object,
    effective_market_date: object,
    mode: object = "current",
    as_of_date: object = None,
    existing_case: object = None,
) -> tuple[dict[str, Any], list[str]]:
    """Migrate only one target company's checkpoint and human theses.

    Corrupt or non-v3 input yields a warning and a valid empty case.  Passing
    the returned case back as ``existing_case`` makes the operation idempotent.
    """
    clean_company = normalise_company_identity(company)
    target = clean_company["canonical_code"]
    warnings: list[str] = []
    valid_v3 = (
        isinstance(legacy_state, Mapping)
        and not isinstance(legacy_state.get("version"), bool)
        and legacy_state.get("version") == LEGACY_STORAGE_VERSION
    )
    if valid_v3:
        checkpoint = _normalise_checkpoint(
            legacy_state.get("evidence_checkpoints"),
            canonical_code=target,
        )
        hypotheses, invalid_count = _normalise_hypotheses(
            legacy_state.get("research_theses"),
            canonical_code=target,
        )
        if invalid_count:
            warnings.append(
                f"已忽略{invalid_count}条与目标公司匹配但格式损坏的旧研究假设。"
            )
        if len(hypotheses) > MAX_HYPOTHESES:
            warnings.append(
                f"旧研究假设超过{MAX_HYPOTHESES}条；迁移已停止，未静默淘汰。"
            )
            raise ResearchCaseCapacityError(
                f"旧研究假设超过案件容量{MAX_HYPOTHESES}。"
            )
    else:
        checkpoint = None
        hypotheses = []
        warnings.append("旧浏览器研究状态损坏或不是version 3；已建立空案件。")

    migration_id = _migration_id(
        canonical_code=target,
        valid_v3=valid_v3,
        checkpoint=checkpoint,
        hypotheses=hypotheses,
    )

    if existing_case is None:
        case = new_research_case(
            case_id,
            clean_company,
            mode=mode,
            as_of_date=as_of_date,
            effective_market_date=effective_market_date,
            created_at=migrated_at,
        )
    else:
        validate_research_case(existing_case)
        case = deepcopy(dict(existing_case))
        if case["case_id"] != case_id:
            raise ResearchCaseValidationError("existing_case.case_id不匹配。")
        if case["company"]["canonical_code"] != target:
            raise ResearchCaseValidationError("existing_case公司身份不匹配。")

    if migration_id in case["migration_ids"]:
        return case, warnings
    if len(case["migration_ids"]) >= MAX_MIGRATION_IDS:
        raise ResearchCaseCapacityError(
            f"migration_ids已达到容量{MAX_MIGRATION_IDS}。"
        )

    existing_by_id = {
        item["hypothesis_id"]: item for item in case["hypotheses"]
    }
    new_ids = {
        item["hypothesis_id"]
        for item in hypotheses
        if item["hypothesis_id"] not in existing_by_id
    }
    if len(existing_by_id) + len(new_ids) > MAX_HYPOTHESES:
        raise ResearchCaseCapacityError(
            f"迁移后hypotheses将超过容量{MAX_HYPOTHESES}。"
        )
    for hypothesis in hypotheses:
        existing_by_id[hypothesis["hypothesis_id"]] = deepcopy(hypothesis)
    case["hypotheses"] = [
        existing_by_id[key] for key in sorted(existing_by_id)
    ]
    if checkpoint is not None:
        case["tracking"]["evidence_checked_at"] = checkpoint

    if checkpoint is not None or hypotheses:
        if len(case["audit_log"]) >= MAX_AUDIT_LOG:
            raise ResearchCaseCapacityError("audit_log已达到容量100。")
        case["audit_log"].append(
            {
                "at": str(migrated_at),
                "message": (
                    "已从旧版浏览器研究状态迁移目标公司的证据检查点与人工研究假设。"
                ),
            }
        )
    case["migration_ids"].append(migration_id)
    case["revision"] += 1
    case["updated_at"] = str(migrated_at)
    case["readiness"] = calculate_readiness(case)
    validate_research_case(case)
    return case, warnings
