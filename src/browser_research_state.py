"""Bound and validate device-local recent research and watchlist state."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any


STORAGE_VERSION = 2
MAX_RECENT_RESEARCH = 6
MAX_LOCAL_WATCHLIST = 5
MAX_EVIDENCE_CHECKPOINTS = 5

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
        }
        or company is None
    ):
        return current

    timestamp = command.get("timestamp")
    timestamp = timestamp[:40] if isinstance(timestamp, str) else ""
    if action == "save_evidence_checkpoint":
        if not timestamp:
            return current
        try:
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
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
    else:
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

    current["last_command_id"] = command_id[:80]
    current["storage_status"] = "available"
    return current
