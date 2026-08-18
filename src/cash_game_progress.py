"""Safe, device-local progress snapshots for ``The Missing Cash`` game.

This module deliberately has no Streamlit or browser dependency.  The page
layer can serialise the returned dictionary to ``localStorage`` and later
restore it into ``st.session_state``.  Both directions pass through the same
small allow-list so that stale, oversized or manually edited browser data
cannot inject arbitrary session keys.
"""

from __future__ import annotations

from datetime import date
from numbers import Integral
import re
from typing import Any, Mapping, MutableMapping
import unicodedata

from src.cash_game_characters import normalise_keepsake_ids


# Version 2 deliberately starts a fresh case after the game-shell redesign.
# The earlier prototype stored a player before the cinematic intake existed,
# which could make returning testers skip the new in-game name scene entirely.
CASH_GAME_PROGRESS_VERSION = 2

_ALLOWED_STAGES = frozenset(
    {
        "briefing",
        "practice",
        "timing_completed",
        "investigation",
        "reading",
        "cross_check",
        "evidence",
        "evidence_completed",
        "defense",
        "defense_failed",
        "case_completed",
        "migration",
        "migration_completed",
    }
)

_INTEGER_FIELDS: dict[str, tuple[int, int, int]] = {
    # Monotonic per-change checkpoint version. It stays below the
    # largest exactly representable JavaScript integer so the browser can use
    # it to reject stale writes from an older open tab.
    "cash_game_progress_revision": (0, 9_000_000_000_000_000, 0),
    "cash_case_attempt_index": (0, 10_000, 0),
    # Scene-three has its own small schema so an old form-based checkpoint
    # cannot skip the new interactive dual-clock investigation.
    "cash_dual_clock_version": (0, 1, 0),
    "cash_dual_clock_revision": (0, 100, 0),
    # Stages five through seven share one evidence-laboratory checkpoint.
    # Its private sub-version lets the app migrate the former checkbox scenes
    # without discarding the player's earlier case progress.
    "cash_evidence_lab_version": (0, 1, 0),
    "cash_evidence_lab_revision": (0, 1_000_000, 0),
    "cash_evidence_attempt_index": (0, 10_000, 0),
    # Stage eight has a separate interaction schema and per-command revision.
    "cash_defense_committee_version": (0, 1, 0),
    "cash_defense_committee_revision": (0, 1_000_000, 0),
    "cash_defense_lives": (0, 3, 3),
    "cash_defense_round_index": (0, 2, 0),
    "cash_defense_attempt_index": (0, 10_000, 0),
    "historical_game_mission_reasoning_attempt": (0, 10_000, 0),
}

_TEXT_FIELDS: dict[str, int] = {
    "cash_case_last_explanation": 4_000,
    "cash_cross_check_explanation": 4_000,
    "cash_evidence_explanation": 6_000,
    "historical_prefill_context": 200,
    "historical_game_mission_reasoning": 4_000,
}

_BOOLEAN_FIELDS = frozenset(
    {
        "cash_identity_required",
        "cash_clock_assignment_unlocked",
        "cash_gap_hypothesis_unlocked",
        "cash_investigation_orders_unlocked",
    }
)

_CASH_DUAL_CLOCK_PHASES = frozenset(
    {"routes", "hypothesis", "orders", "door"}
)

_CASH_EVIDENCE_LAB_PHASES = frozenset(
    {"reading", "classification", "chain"}
)

_IDENTIFIER_FIELDS = frozenset(
    {
        "cash_timing_order_question_id",
        "cash_timing_order_completed_question_id",
        "cash_evidence_lab_task_id",
        "cash_defense_committee_task_id",
        "historical_game_mission_id",
        "historical_game_mission_date_completed",
        "historical_game_mission_completed",
    }
)

_TIMING_EVENT_IDS = frozenset(
    {
        "contract_signed",
        # Kept so a version-2 browser snapshot from the former timeline scene
        # can still be read safely during the migration window.
        "customer_accepted",
        "service_completed",
        "expense_incurred",
        "expense_paid",
        "cash_collected",
        "future_payment_plan",
    }
)

_DATE_FIELDS = frozenset(
    {
        "historical_prefill_date",
        "historical_game_mission_answer",
    }
)

_EVIDENCE_DOCUMENT_IDS = frozenset(
    {
        "executive_slide",
        "contract_clause",
        "celebration_chat",
        "signed_acceptance",
        "ar_subledger",
        "post_period_receipt",
    }
)

_EVIDENCE_LAB_ACCEPTED_FIELD_IDS = frozenset(
    {
        "contract_reference",
        "contract_payment_window",
        "acceptance_date",
        "acceptance_external_seal",
        "ar_year_end_balance",
        "ar_due_status",
        "receipt_date",
        "receipt_bank_match",
    }
)

_EVIDENCE_LAB_CLASSIFICATION_ANSWERS = {
    "contract_term_at_year_end": "year_end_fact",
    "signed_acceptance_before_cutoff": "year_end_fact",
    "year_end_ar_not_due": "year_end_fact",
    "later_bank_receipt": "subsequent_evidence",
    "chat_expectation": "unverified_claim",
    "management_forecast": "unverified_claim",
}

_EVIDENCE_LAB_CHAIN_ANSWERS = {
    "claim_payment_boundary": "contract_clause",
    "claim_completion_before_cutoff": "signed_acceptance",
    "claim_year_end_balance": "ar_subledger",
    "claim_later_cash": "post_period_receipt",
}

_DEFENSE_COMMITTEE_SEAT_IDS = frozenset(
    {"conclusion_strength", "evidence_boundary", "next_action"}
)

_DEFENSE_COMMITTEE_CARD_ID = re.compile(
    r"^(conclusion_strength|evidence_boundary|next_action):card:[1-6]$"
)

_MANAGED_SESSION_KEYS = frozenset(
    {
        "game_player_name",
        "cash_case_stage",
        "cash_dual_clock_phase",
        "cash_game_keepsakes",
        "cash_game_pending_keepsakes",
        "cash_game_used_hints",
        "cash_timing_order_ids",
        "cash_discovered_document_ids",
        "cash_evidence_lab_phase",
        "cash_evidence_lab_reading_viewed_ids",
        "cash_evidence_lab_reading_accepted_ids",
        "cash_evidence_lab_classification_accepted",
        "cash_evidence_lab_chain_accepted",
        "cash_defense_committee_accepted_placements",
        "cash_defense_completed_explanations",
        *_BOOLEAN_FIELDS,
        *_INTEGER_FIELDS,
        *_TEXT_FIELDS,
        *_IDENTIFIER_FIELDS,
        *_DATE_FIELDS,
    }
)

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _clean_text(value: object, max_chars: int) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = "".join(
        character
        for character in value.strip()
        if character in {"\n", "\t"}
        or not unicodedata.category(character).startswith("C")
    )
    if not cleaned:
        return None
    return cleaned[:max_chars]


def _clean_player_name(value: object) -> str | None:
    cleaned = _clean_text(value, 128)
    if cleaned is None:
        return None
    # A player name is one display line; the game UI allows at most 12 chars.
    normalised = " ".join(cleaned.split())
    return normalised[:12] or None


def _bounded_integer(
    value: object,
    minimum: int,
    maximum: int,
    default: int,
) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        return default
    return max(minimum, min(int(value), maximum))


def _clean_identifier(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not _SAFE_IDENTIFIER.fullmatch(candidate):
        return None
    return candidate


def _clean_iso_date(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if len(candidate) != 10:
        return None
    try:
        parsed = date.fromisoformat(candidate)
    except ValueError:
        return None
    if not 1990 <= parsed.year <= 2100:
        return None
    return parsed.isoformat()


def normalise_cash_game_progress_snapshot(
    value: object,
) -> dict[str, Any] | None:
    """Return a bounded JSON-safe progress snapshot or ``None``.

    The player name is the marker that a game has actually started.  Unknown
    keys, transient feedback and widget state are intentionally discarded.
    Invalid optional values are omitted; bounded counters fall back to their
    safe defaults.
    """
    if not isinstance(value, Mapping):
        return None

    # Do not hydrate checkpoints created by the earlier page-like prototype.
    # Version-less values are also rejected because every legitimate browser
    # snapshot written by this module carries an explicit schema version.
    if value.get("version") != CASH_GAME_PROGRESS_VERSION:
        return None

    player_name = _clean_player_name(value.get("game_player_name"))
    if player_name is None:
        return None

    stage_value = value.get("cash_case_stage")
    stage = stage_value if stage_value in _ALLOWED_STAGES else "briefing"
    snapshot: dict[str, Any] = {
        "version": CASH_GAME_PROGRESS_VERSION,
        "game_player_name": player_name,
        "cash_case_stage": stage,
    }

    for field, (minimum, maximum, default) in _INTEGER_FIELDS.items():
        snapshot[field] = _bounded_integer(
            value.get(field),
            minimum,
            maximum,
            default,
        )

    completed_explanations = value.get(
        "cash_defense_completed_explanations"
    )
    safe_explanations: list[str] = []
    if isinstance(completed_explanations, (list, tuple)):
        for explanation in completed_explanations[:3]:
            cleaned = _clean_text(explanation, 4_000)
            if cleaned is not None:
                safe_explanations.append(cleaned)
    snapshot["cash_defense_completed_explanations"] = safe_explanations

    discovered_ids = value.get("cash_discovered_document_ids")
    safe_discovered_ids: list[str] = []
    if isinstance(discovered_ids, (list, tuple)):
        for document_id in discovered_ids:
            if (
                isinstance(document_id, str)
                and document_id in _EVIDENCE_DOCUMENT_IDS
                and document_id not in safe_discovered_ids
            ):
                safe_discovered_ids.append(document_id)
    snapshot["cash_discovered_document_ids"] = safe_discovered_ids

    viewed_ids = value.get("cash_evidence_lab_reading_viewed_ids")
    safe_viewed_ids: list[str] = []
    if isinstance(viewed_ids, (list, tuple)):
        for document_id in viewed_ids:
            if (
                isinstance(document_id, str)
                and document_id in _EVIDENCE_DOCUMENT_IDS
                and document_id not in safe_viewed_ids
            ):
                safe_viewed_ids.append(document_id)
    snapshot["cash_evidence_lab_reading_viewed_ids"] = safe_viewed_ids

    accepted_field_ids = value.get(
        "cash_evidence_lab_reading_accepted_ids"
    )
    safe_accepted_field_ids: list[str] = []
    if isinstance(accepted_field_ids, (list, tuple)):
        for field_id in accepted_field_ids:
            if (
                isinstance(field_id, str)
                and field_id in _EVIDENCE_LAB_ACCEPTED_FIELD_IDS
                and field_id not in safe_accepted_field_ids
            ):
                safe_accepted_field_ids.append(field_id)
    snapshot["cash_evidence_lab_reading_accepted_ids"] = (
        safe_accepted_field_ids
    )

    placements = value.get("cash_evidence_lab_classification_accepted")
    safe_placements: dict[str, str] = {}
    if isinstance(placements, Mapping):
        for item_id, class_id in placements.items():
            if (
                isinstance(item_id, str)
                and isinstance(class_id, str)
                and _EVIDENCE_LAB_CLASSIFICATION_ANSWERS.get(item_id)
                == class_id
            ):
                safe_placements[item_id] = class_id
    snapshot["cash_evidence_lab_classification_accepted"] = safe_placements

    links = value.get("cash_evidence_lab_chain_accepted")
    safe_links: dict[str, str] = {}
    if isinstance(links, Mapping):
        for claim_id, document_id in links.items():
            if (
                isinstance(claim_id, str)
                and isinstance(document_id, str)
                and _EVIDENCE_LAB_CHAIN_ANSWERS.get(claim_id)
                == document_id
            ):
                safe_links[claim_id] = document_id
    snapshot["cash_evidence_lab_chain_accepted"] = safe_links

    committee_placements = value.get(
        "cash_defense_committee_accepted_placements"
    )
    safe_committee_placements: dict[str, str] = {}
    if isinstance(committee_placements, Mapping):
        for seat_id, card_id in committee_placements.items():
            if (
                isinstance(seat_id, str)
                and seat_id in _DEFENSE_COMMITTEE_SEAT_IDS
                and isinstance(card_id, str)
                and _DEFENSE_COMMITTEE_CARD_ID.fullmatch(card_id)
                and card_id.startswith(f"{seat_id}:card:")
            ):
                safe_committee_placements[seat_id] = card_id
    # This is only a structural browser allow-list.  ``src.app`` re-evaluates
    # every restored mapping against the current server challenge before it is
    # exposed as accepted progress.
    snapshot["cash_defense_committee_accepted_placements"] = (
        safe_committee_placements
    )

    timing_order_ids = value.get("cash_timing_order_ids")
    safe_timing_order_ids: list[str] = []
    if isinstance(timing_order_ids, (list, tuple)):
        for event_id in timing_order_ids[:4]:
            if (
                isinstance(event_id, str)
                and event_id in _TIMING_EVENT_IDS
                and event_id not in safe_timing_order_ids
            ):
                safe_timing_order_ids.append(event_id)
    snapshot["cash_timing_order_ids"] = safe_timing_order_ids

    snapshot["cash_game_keepsakes"] = normalise_keepsake_ids(
        value.get("cash_game_keepsakes")
    )
    owned_keepsakes = set(snapshot["cash_game_keepsakes"])
    snapshot["cash_game_pending_keepsakes"] = [
        keepsake_id
        for keepsake_id in normalise_keepsake_ids(
            value.get("cash_game_pending_keepsakes")
        )
        if keepsake_id not in owned_keepsakes
    ]
    snapshot["cash_game_used_hints"] = [
        keepsake_id
        for keepsake_id in normalise_keepsake_ids(
            value.get("cash_game_used_hints")
        )
        if keepsake_id in owned_keepsakes
    ]

    dual_clock_phase = value.get("cash_dual_clock_phase")
    if dual_clock_phase in _CASH_DUAL_CLOCK_PHASES:
        snapshot["cash_dual_clock_phase"] = dual_clock_phase

    evidence_lab_phase = value.get("cash_evidence_lab_phase")
    if evidence_lab_phase in _CASH_EVIDENCE_LAB_PHASES:
        snapshot["cash_evidence_lab_phase"] = evidence_lab_phase

    for field in _BOOLEAN_FIELDS:
        value_for_field = value.get(field)
        if isinstance(value_for_field, bool):
            snapshot[field] = value_for_field

    for field, max_chars in _TEXT_FIELDS.items():
        cleaned = _clean_text(value.get(field), max_chars)
        if cleaned is not None:
            snapshot[field] = cleaned

    for field in _IDENTIFIER_FIELDS:
        cleaned = _clean_identifier(value.get(field))
        if cleaned is not None:
            snapshot[field] = cleaned

    for field in _DATE_FIELDS:
        cleaned = _clean_iso_date(value.get(field))
        if cleaned is not None:
            snapshot[field] = cleaned

    if (
        snapshot["cash_case_stage"] == "migration_completed"
        and "historical_game_mission_completed" not in snapshot
    ):
        # A hand-edited or partially written checkpoint must not trap the
        # visitor on a locked honour page. Return to the recoverable mission.
        snapshot["cash_case_stage"] = "migration"

    return snapshot


def build_cash_game_progress_snapshot(
    state: Mapping[str, object],
) -> dict[str, Any] | None:
    """Build a safe browser-storage payload from session-like state."""
    # Streamlit session state does not carry a schema version. Add the current
    # one only while serialising; browser-supplied snapshots remain subject to
    # the strict version gate in ``normalise_cash_game_progress_snapshot``.
    return normalise_cash_game_progress_snapshot(
        {**state, "version": CASH_GAME_PROGRESS_VERSION}
    )


def restore_cash_game_progress_snapshot(
    state: MutableMapping[str, object],
    snapshot: object,
) -> bool:
    """Replace durable game fields in ``state`` from a safe snapshot.

    Existing managed optional fields are cleared first so that a restored
    earlier checkpoint cannot accidentally inherit later progress from the
    current server session.  Unrelated page and widget state is preserved.
    ``False`` means the supplied snapshot was invalid and no mutation occurred.
    """
    normalised = normalise_cash_game_progress_snapshot(snapshot)
    if normalised is None:
        return False

    for key in _MANAGED_SESSION_KEYS:
        state.pop(key, None)
    for key, value in normalised.items():
        if key != "version":
            state[key] = value
    return True


def clear_cash_game_progress_state(
    state: MutableMapping[str, object],
) -> None:
    """Remove only durable game fields during an explicit schema upgrade."""
    for key in _MANAGED_SESSION_KEYS:
        state.pop(key, None)


def browser_cash_game_snapshot_wins(
    current: object,
    browser: object,
    *,
    base_revision: int,
) -> bool:
    """Return whether a browser checkpoint must replace this tab's state.

    The obvious case is a strictly newer browser revision.  The less obvious
    case is two open tabs that both advanced from the same revision: both can
    produce revision ``n + 1``, but only the first write owns the browser
    checkpoint.  When this tab still reports an older base revision and the
    equal-revision payloads differ, the already stored browser checkpoint wins
    so a stale tab cannot roll the game backwards.
    """
    browser_snapshot = normalise_cash_game_progress_snapshot(browser)
    if browser_snapshot is None:
        return False

    current_snapshot = normalise_cash_game_progress_snapshot(current)
    if current_snapshot is None:
        return True

    browser_revision = int(
        browser_snapshot.get("cash_game_progress_revision", 0)
    )
    current_revision = int(
        current_snapshot.get("cash_game_progress_revision", 0)
    )
    if browser_revision > current_revision:
        return True
    if browser_revision != current_revision:
        return False
    if browser_revision <= max(int(base_revision), 0):
        return False

    browser_payload = {
        key: value
        for key, value in browser_snapshot.items()
        if key != "cash_game_progress_revision"
    }
    current_payload = {
        key: value
        for key, value in current_snapshot.items()
        if key != "cash_game_progress_revision"
    }
    return browser_payload != current_payload


# American-spelling alias for callers that use ``normalize`` elsewhere.
normalize_cash_game_progress_snapshot = normalise_cash_game_progress_snapshot


__all__ = [
    "CASH_GAME_PROGRESS_VERSION",
    "browser_cash_game_snapshot_wins",
    "build_cash_game_progress_snapshot",
    "clear_cash_game_progress_state",
    "normalise_cash_game_progress_snapshot",
    "normalize_cash_game_progress_snapshot",
    "restore_cash_game_progress_snapshot",
]
