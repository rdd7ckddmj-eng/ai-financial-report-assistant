"""Bound and validate device-local recent research and watchlist state."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from urllib.parse import urlparse


STORAGE_VERSION = 3
MAX_RECENT_RESEARCH = 6
MAX_LOCAL_WATCHLIST = 5
MAX_EVIDENCE_CHECKPOINTS = 5
MAX_RESEARCH_THESES = 10

THESIS_TOPICS = (
    "财务与业绩",
    "经营事项",
    "资本运作",
    "治理与风险",
    "其他",
)
THESIS_STATUSES = (
    "待核验",
    "暂有证据支持",
    "出现反方证据",
    "已失效",
)

_COMPANY_FIELDS = (
    "code",
    "name",
    "exchange",
    "exchange_name",
    "canonical_code",
)


def empty_browser_research_state() -> dict[str, Any]:
    """Return a fresh, JSON-serialisable local research state."""
    return {
        "version": STORAGE_VERSION,
        "recent": [],
        "watchlist": [],
        "evidence_checkpoints": [],
        "research_theses": [],
        "last_command_id": None,
        "storage_status": "pending",
    }


def normalise_local_company(value: object) -> dict[str, str] | None:
    """Keep only a small, safe public-company identity from browser input."""
    if not isinstance(value, Mapping):
        return None

    company: dict[str, str] = {}
    for field in _COMPANY_FIELDS:
        raw = value.get(field)
        if not isinstance(raw, str) or not raw.strip():
            return None
        company[field] = raw.strip()[:80]

    code = company["code"]
    if len(code) != 6 or not code.isdigit():
        return None
    if company["canonical_code"] != f"{code}.{company['exchange']}":
        return None

    for field in ("last_researched_at", "added_at"):
        raw = value.get(field)
        if isinstance(raw, str) and raw.strip():
            company[field] = raw.strip()[:40]
    return company


def _normalise_company_list(
    value: object,
    *,
    limit: int,
) -> list[dict[str, str]]:
    """Deduplicate and bound one untrusted browser-provided company list."""
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
    ):
        return []

    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in value:
        company = normalise_local_company(raw)
        if company is None:
            continue
        canonical_code = company["canonical_code"]
        if canonical_code in seen:
            continue
        seen.add(canonical_code)
        result.append(company)
        if len(result) >= limit:
            break
    return result


def _normalise_evidence_checkpoint(value: object) -> dict[str, str] | None:
    """Validate one device-local evidence-check time and company identity."""
    company = normalise_local_company(value)
    if company is None or not isinstance(value, Mapping):
        return None
    checked_at = value.get("evidence_checked_at")
    if not isinstance(checked_at, str) or not checked_at.strip():
        return None
    cleaned = checked_at.strip()[:40]
    try:
        datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError:
        return None
    company["evidence_checked_at"] = cleaned
    return company


def _normalise_checkpoint_list(value: object) -> list[dict[str, str]]:
    """Deduplicate and bound browser-provided evidence checkpoints."""
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
    ):
        return []
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in value:
        checkpoint = _normalise_evidence_checkpoint(raw)
        if checkpoint is None:
            continue
        canonical_code = checkpoint["canonical_code"]
        if canonical_code in seen:
            continue
        seen.add(canonical_code)
        result.append(checkpoint)
        if len(result) >= MAX_EVIDENCE_CHECKPOINTS:
            break
    return result


def _clean_text(
    value: object,
    *,
    limit: int,
    required: bool = False,
) -> str | None:
    if not isinstance(value, str):
        return None if required else ""
    cleaned = " ".join(value.split()).strip()[:limit]
    if required and not cleaned:
        return None
    return cleaned


def _is_iso_datetime(value: str) -> bool:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _is_allowed_official_url(value: str) -> bool:
    parsed = urlparse(value)
    hostname = (parsed.hostname or "").lower()
    allowed_hosts = (
        "cninfo.com.cn",
        "sse.com.cn",
        "szse.cn",
        "bse.cn",
    )
    return parsed.scheme in {"http", "https"} and any(
        hostname == host or hostname.endswith(f".{host}")
        for host in allowed_hosts
    )


def _normalise_research_thesis(value: object) -> dict[str, str] | None:
    """Validate one browser-stored research hypothesis and review record."""
    company = normalise_local_company(value)
    if company is None or not isinstance(value, Mapping):
        return None
    thesis_id = _clean_text(value.get("thesis_id"), limit=80, required=True)
    hypothesis = _clean_text(
        value.get("hypothesis"),
        limit=240,
        required=True,
    )
    confirmation = _clean_text(
        value.get("confirmation_criteria"),
        limit=360,
        required=True,
    )
    invalidation = _clean_text(
        value.get("invalidation_criteria"),
        limit=360,
        required=True,
    )
    topic = value.get("topic")
    status = value.get("status")
    created_at = _clean_text(
        value.get("created_at"),
        limit=40,
        required=True,
    )
    updated_at = _clean_text(
        value.get("updated_at"),
        limit=40,
        required=True,
    )
    if (
        thesis_id is None
        or hypothesis is None
        or confirmation is None
        or invalidation is None
        or topic not in THESIS_TOPICS
        or status not in THESIS_STATUSES
        or created_at is None
        or updated_at is None
        or not _is_iso_datetime(created_at)
        or not _is_iso_datetime(updated_at)
    ):
        return None

    company.update(
        {
            "thesis_id": thesis_id,
            "hypothesis": hypothesis,
            "confirmation_criteria": confirmation,
            "invalidation_criteria": invalidation,
            "topic": str(topic),
            "status": str(status),
            "created_at": created_at,
            "updated_at": updated_at,
        }
    )
    review_note = _clean_text(value.get("review_note"), limit=360)
    if review_note:
        company["review_note"] = review_note

    evidence_title = _clean_text(value.get("evidence_title"), limit=300)
    evidence_url = _clean_text(value.get("evidence_url"), limit=500)
    evidence_date = _clean_text(value.get("evidence_date"), limit=10)
    if (
        evidence_title
        and evidence_url
        and evidence_date
        and _is_allowed_official_url(evidence_url)
    ):
        try:
            datetime.fromisoformat(evidence_date).date()
        except ValueError:
            pass
        else:
            company.update(
                {
                    "evidence_title": evidence_title,
                    "evidence_url": evidence_url,
                    "evidence_date": evidence_date,
                }
            )
    return company


def _normalise_thesis_list(value: object) -> list[dict[str, str]]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
    ):
        return []
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in value:
        thesis = _normalise_research_thesis(raw)
        if thesis is None or thesis["thesis_id"] in seen:
            continue
        seen.add(thesis["thesis_id"])
        result.append(thesis)
        if len(result) >= MAX_RESEARCH_THESES:
            break
    return result


def normalise_browser_research_state(value: object) -> dict[str, Any]:
    """Validate localStorage content before it reaches the product UI."""
    if not isinstance(value, Mapping):
        return empty_browser_research_state()

    command_id = value.get("last_command_id")
    if not isinstance(command_id, str) or not command_id.strip():
        command_id = None
    elif len(command_id) > 80:
        command_id = command_id[:80]

    storage_status = value.get("storage_status")
    if storage_status not in {"pending", "available", "unavailable"}:
        storage_status = "pending"

    return {
        "version": STORAGE_VERSION,
        "recent": _normalise_company_list(
            value.get("recent"),
            limit=MAX_RECENT_RESEARCH,
        ),
        "watchlist": _normalise_company_list(
            value.get("watchlist"),
            limit=MAX_LOCAL_WATCHLIST,
        ),
        "evidence_checkpoints": _normalise_checkpoint_list(
            value.get("evidence_checkpoints")
        ),
        "research_theses": _normalise_thesis_list(
            value.get("research_theses")
        ),
        "last_command_id": command_id,
        "storage_status": storage_status,
    }


def apply_browser_research_command(
    state: object,
    command: object,
) -> dict[str, Any]:
    """Apply the same bounded command rules used by the browser component."""
    current = normalise_browser_research_state(state)
    if not isinstance(command, Mapping):
        return current

    command_id = command.get("id")
    action = command.get("action")
    company = normalise_local_company(command.get("company"))
    if (
        not isinstance(command_id, str)
        or not command_id.strip()
        or command_id == current["last_command_id"]
        or action not in {
            "record_research",
            "toggle_watchlist",
            "save_evidence_checkpoint",
            "save_research_thesis",
            "update_research_thesis",
            "delete_research_thesis",
        }
        or company is None
    ):
        return current

    timestamp = command.get("timestamp")
    timestamp = timestamp[:40] if isinstance(timestamp, str) else ""
    if action in {
        "save_evidence_checkpoint",
        "save_research_thesis",
        "update_research_thesis",
    }:
        if not timestamp:
            return current
        if not _is_iso_datetime(timestamp):
            return current
    canonical_code = company["canonical_code"]

    if action == "record_research":
        if timestamp:
            company["last_researched_at"] = timestamp
        recent = [
            item
            for item in current["recent"]
            if item["canonical_code"] != canonical_code
        ]
        current["recent"] = [company, *recent][:MAX_RECENT_RESEARCH]
    elif action == "toggle_watchlist":
        existing = [
            item
            for item in current["watchlist"]
            if item["canonical_code"] != canonical_code
        ]
        if len(existing) == len(current["watchlist"]):
            if timestamp:
                company["added_at"] = timestamp
            current["watchlist"] = [
                company,
                *existing,
            ][:MAX_LOCAL_WATCHLIST]
        else:
            current["watchlist"] = existing
    elif action == "save_evidence_checkpoint":
        if timestamp:
            company["evidence_checked_at"] = timestamp
        checkpoints = [
            item
            for item in current["evidence_checkpoints"]
            if item["canonical_code"] != canonical_code
        ]
        current["evidence_checkpoints"] = [
            company,
            *checkpoints,
        ][:MAX_EVIDENCE_CHECKPOINTS]
    elif action == "save_research_thesis":
        candidate = {
            **company,
            "thesis_id": command.get("thesis_id"),
            "hypothesis": command.get("hypothesis"),
            "confirmation_criteria": command.get("confirmation_criteria"),
            "invalidation_criteria": command.get("invalidation_criteria"),
            "topic": command.get("topic"),
            "status": "待核验",
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        thesis = _normalise_research_thesis(candidate)
        if thesis is None:
            return current
        existing = [
            item
            for item in current["research_theses"]
            if item["thesis_id"] != thesis["thesis_id"]
        ]
        current["research_theses"] = [
            thesis,
            *existing,
        ][:MAX_RESEARCH_THESES]
    elif action == "update_research_thesis":
        thesis_id = _clean_text(
            command.get("thesis_id"),
            limit=80,
            required=True,
        )
        status = command.get("status")
        existing = next(
            (
                item
                for item in current["research_theses"]
                if item["thesis_id"] == thesis_id
                and item["canonical_code"] == canonical_code
            ),
            None,
        )
        if existing is None or status not in THESIS_STATUSES:
            return current
        candidate = {
            **existing,
            "status": status,
            "updated_at": timestamp,
            "review_note": command.get("review_note"),
            "evidence_title": command.get("evidence_title"),
            "evidence_url": command.get("evidence_url"),
            "evidence_date": command.get("evidence_date"),
        }
        thesis = _normalise_research_thesis(candidate)
        if thesis is None:
            return current
        current["research_theses"] = [
            thesis if item["thesis_id"] == thesis_id else item
            for item in current["research_theses"]
        ]
    else:
        thesis_id = _clean_text(
            command.get("thesis_id"),
            limit=80,
            required=True,
        )
        if thesis_id is None:
            return current
        current["research_theses"] = [
            item
            for item in current["research_theses"]
            if not (
                item["thesis_id"] == thesis_id
                and item["canonical_code"] == canonical_code
            )
        ]

    current["last_command_id"] = command_id[:80]
    current["storage_status"] = "available"
    return current
