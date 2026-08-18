"""Full-screen Stage 8 review-committee browser component.

The browser keeps only the player's current placement draft.  Python remains
authoritative for lives, accepted rounds and whether any statement is sound.
The answer-free public task is passed through unchanged and the component
emits a strict, short-lived command envelope for every formal submission.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import streamlit as st


_STATIC_DIR = Path(__file__).resolve().parent / "static"
_COMPONENT_HTML = """
<main class="committee-game" data-component="cash-defense-committee">
  <p class="committee-boot-status" role="status">正在点亮审查委员会……</p>
</main>
"""
_COMPONENT_CSS = (
    _STATIC_DIR / "cash-defense-committee-game.css"
).read_text(encoding="utf-8")
_COMPONENT_JS = (
    _STATIC_DIR / "cash-defense-committee-game.js"
).read_text(encoding="utf-8")


_CASH_DEFENSE_COMMITTEE = st.components.v2.component(
    name="wfz_cash_defense_committee",
    html=_COMPONENT_HTML,
    css=_COMPONENT_CSS,
    js=_COMPONENT_JS,
)


def render_cash_defense_committee(
    *,
    state: Mapping[str, Any],
    task_id: str,
    revision: int,
    draft_storage_key: str = "wfz_cash_defense_committee_draft",
    key: str = "wfz_cash_defense_committee",
    on_command_change: Callable[[], None] | None = None,
) -> Any:
    """Render the three-seat hearing and return a transient command result.

    Recommended answer-free ``state`` fields are:

    - ``task``: ``build_cash_defense_committee_public_task(...)``.
    - ``player_name``, server-owned ``lives`` and optional ``max_lives``.
    - ``passed_rounds``: already approved round numbers or zero-based indices.
    - ``progress.accepted_placements`` for seats locked in this challenge.
    - ``evaluation`` and ``acknowledged_command_id`` for returning accepted
      and rejected seat IDs after Python has evaluated one command.
    - ``evaluation_task_id``: the task that produced ``evaluation``.  It must
      match the current task before the browser applies accepted/rejected IDs.
    - ``keepsake_discovered``: server-owned ownership/pending state for the
      hidden Stage 8 ``逆向黑棋``.
    - optional ``feedback`` and ``npc_by_seat`` presentation data.

    The formal command contains exactly ``schema_version``, ``command_id``,
    ``task_id``, ``revision``, ``action`` and ``placements``.  Its action is
    ``submit_committee_statement``.  Toolbar commands use exactly the common
    five-field envelope and one of ``go_back``, ``rename_player``,
    ``restart_game``, ``exit_game`` or ``discover_keepsake``.
    """

    clean_task_id = str(task_id).strip()[:160]
    if not clean_task_id:
        raise ValueError("task_id must not be empty")
    clean_revision = int(revision)
    if clean_revision < 0:
        raise ValueError("revision must be non-negative")
    clean_storage_key = str(draft_storage_key).strip()[:180]
    if not clean_storage_key:
        clean_storage_key = "wfz_cash_defense_committee_draft"

    callback = on_command_change or (lambda: None)
    return _CASH_DEFENSE_COMMITTEE(
        data={
            "schema_version": 1,
            "task_id": clean_task_id,
            "revision": clean_revision,
            "draft_storage_key": clean_storage_key,
            "state": dict(state),
        },
        key=key,
        width="stretch",
        height="content",
        on_command_change=callback,
    )


__all__ = ["render_cash_defense_committee"]
