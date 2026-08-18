"""Interactive browser component for the dual-clock investigation scene.

The component deliberately owns presentation only.  It never receives the
answer key and therefore cannot decide whether a player's move is correct.
Every move is emitted as a short-lived command for Python to validate; the
authoritative state returned by Python is then rendered on the next rerun.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import streamlit as st


_STATIC_DIR = Path(__file__).resolve().parent / "static"
_COMPONENT_HTML = """
<main class="dc-game" data-component="cash-dual-clock-game">
  <p class="dc-boot-status" role="status">正在接入双时钟调查室……</p>
</main>
"""
_COMPONENT_CSS = (_STATIC_DIR / "cash-dual-clock-game.css").read_text(
    encoding="utf-8"
)
_COMPONENT_JS = (_STATIC_DIR / "cash-dual-clock-game.js").read_text(
    encoding="utf-8"
)


_CASH_DUAL_CLOCK_GAME = st.components.v2.component(
    name="wfz_cash_dual_clock_game",
    html=_COMPONENT_HTML,
    css=_COMPONENT_CSS,
    js=_COMPONENT_JS,
)


def render_cash_dual_clock_game(
    *,
    state: Mapping[str, Any],
    question_id: str,
    revision: int,
    key: str = "wfz_cash_dual_clock_game",
    draft_storage_key: str = "wfz.cash-dual-clock-draft.v1",
    on_command_change: Callable[[], None] | None = None,
) -> Any:
    """Render Stage 3 and return the component result.

    ``state`` is the Python-approved public view.  Suggested keys are:

    - ``phase``: ``routes``, ``hypothesis``, ``orders`` or ``door``;
    - ``cards`` / ``zones`` for the fact-classification scene;
    - ``gap_token`` / ``hypothesis_slots`` for the hypothesis scene;
    - ``materials`` / ``evidence_pockets`` for the investigation-order scene;
    - ``issued_order`` / ``door`` for the final access scene;
    - ``npc``, ``feedback``, ``progress`` and ``accepted`` for presentation.

    For local-draft reconciliation, Python should return ``placements`` plus
    ``acknowledged_command_id`` after validating a submit command.  The
    component applies each acknowledgement exactly once, then keeps later
    unsubmitted moves even if Streamlit performs an unrelated rerun.

    Emitted actions are ``submit_routes`` (``bins``), ``submit_hypothesis``
    (``hypothesis_id``), ``submit_orders`` (``pockets`` maps target IDs to
    material IDs and ``discarded`` contains one material), ``open_door``, and
    ``discover_keepsake``.  The final two actions contain no extra fields.
    The in-scene toolbar emits ``go_back``, ``rename_player``,
    ``restart_game`` and ``exit_game`` with the same common envelope; the
    page controller handles those before the finance rule engine.

    No answer key should be included.  A player action appears transiently as
    ``result.command`` and always includes ``schema_version``, ``command_id``,
    ``question_id`` and ``revision``.  Python must revalidate every field.
    """

    clean_question_id = str(question_id).strip()[:80]
    if not clean_question_id:
        raise ValueError("question_id must not be empty")
    clean_revision = int(revision)
    if clean_revision < 0:
        raise ValueError("revision must be non-negative")

    callback = on_command_change or (lambda: None)
    return _CASH_DUAL_CLOCK_GAME(
        data={
            "schema_version": 1,
            "question_id": clean_question_id,
            "revision": clean_revision,
            "draft_storage_key": str(draft_storage_key).strip()[:180],
            "state": dict(state),
        },
        key=key,
        width="stretch",
        height="stretch",
        on_command_change=callback,
    )


__all__ = ["render_cash_dual_clock_game"]
