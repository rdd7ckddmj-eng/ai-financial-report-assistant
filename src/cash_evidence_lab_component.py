"""Interactive Stage 5--7 evidence laboratory browser component.

The browser owns only the player's current board draft.  Python remains the
authority for every accepted highlight, classification and evidence link; the
public task never contains an answer key.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import streamlit as st


_STATIC_DIR = Path(__file__).resolve().parent / "static"
_COMPONENT_HTML = """
<main class="evidence-lab" data-component="cash-evidence-lab">
  <p class="lab-boot-status" role="status">正在接通证据实验室……</p>
</main>
"""
_COMPONENT_CSS = (_STATIC_DIR / "cash-evidence-lab-game.css").read_text(
    encoding="utf-8"
)
_COMPONENT_JS = (_STATIC_DIR / "cash-evidence-lab-game.js").read_text(
    encoding="utf-8"
)


_CASH_EVIDENCE_LAB = st.components.v2.component(
    name="wfz_cash_evidence_lab",
    html=_COMPONENT_HTML,
    css=_COMPONENT_CSS,
    js=_COMPONENT_JS,
)


def render_cash_evidence_lab(
    *,
    state: Mapping[str, Any],
    task_id: str,
    revision: int,
    draft_storage_key: str = "wfz_cash_evidence_lab_draft",
    key: str = "wfz_cash_evidence_lab",
    on_command_change: Callable[[], None] | None = None,
) -> Any:
    """Render the continuous evidence laboratory.

    Recommended public ``state`` fields are:

    - ``phase``: ``reading``, ``classification`` or ``chain``.
    - ``task``: the answer-free result of
      ``build_cash_evidence_lab_public_task``.
    - ``progress``: server-approved ``viewed_document_ids``,
      ``accepted_field_ids``, ``accepted_placements`` and ``accepted_links``.
    - ``evaluation`` and ``acknowledged_command_id`` for releasing only the
      rejected current cards/links after a round trip.
    - optional ``npc``, ``feedback``, ``player_name`` and
      ``keepsake_discovered`` presentation fields.

    The three task commands use the strict server schema:
    ``submit_reading``, ``submit_classification`` and ``submit_chain``.
    Toolbar commands and ``discover_keepsake`` use only the common envelope
    and may be handled by the page before task evaluation.
    """

    clean_task_id = str(task_id).strip()[:120]
    if not clean_task_id:
        raise ValueError("task_id must not be empty")
    clean_revision = int(revision)
    if clean_revision < 0:
        raise ValueError("revision must be non-negative")
    clean_storage_key = str(draft_storage_key).strip()[:160]
    if not clean_storage_key:
        clean_storage_key = "wfz_cash_evidence_lab_draft"

    callback = on_command_change or (lambda: None)
    return _CASH_EVIDENCE_LAB(
        data={
            "schema_version": 1,
            "task_id": clean_task_id,
            "revision": clean_revision,
            "draft_storage_key": clean_storage_key,
            "state": dict(state),
        },
        key=key,
        width="stretch",
        height="stretch",
        on_command_change=callback,
    )


__all__ = ["render_cash_evidence_lab"]
