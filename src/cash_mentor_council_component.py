"""Bidirectional Stage 8 epilogue component for the nine-seat council.

The browser renders the council and emits candidate handoffs.  Python remains
authoritative for every keepsake-to-mentor match, so this module deliberately
contains no matching table or other answer data.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import streamlit as st


_STATIC_DIR = Path(__file__).resolve().parent / "static"
_COMPONENT_HTML = """
<main class="mentor-council-game" data-component="cash-mentor-council">
  <p class="council-boot-status" role="status">正在点亮九席会场……</p>
</main>
"""
_COMPONENT_CSS = (_STATIC_DIR / "cash-mentor-council-game.css").read_text(
    encoding="utf-8"
)
_COMPONENT_JS = (_STATIC_DIR / "cash-mentor-council-game.js").read_text(
    encoding="utf-8"
)


_CASH_MENTOR_COUNCIL = st.components.v2.component(
    name="wfz_cash_mentor_council",
    html=_COMPONENT_HTML,
    css=_COMPONENT_CSS,
    js=_COMPONENT_JS,
)


def render_cash_mentor_council(
    *,
    state: Mapping[str, Any],
    task_id: str,
    revision: int,
    key: str = "wfz_cash_mentor_council",
    on_command_change: Callable[[], None] | None = None,
) -> Any:
    """Render the council and return its transient ``command`` trigger.

    Public ``state`` fields:

    - ``player_name``, ``title`` and ``subtitle``.
    - ``mentors``: public identity data (``mentor_id``, ``step``, ``name``,
      ``role``, ``capability`` and ``image_url``).  A server-accepted mentor
      may additionally expose ``matched=True``, ``matched_keepsake`` and
      ``revealed_hint``.  Unmatched mentors must not expose their answer.
    - ``keepsakes``: discovered public items (``keepsake_id``, ``name``,
      ``mark`` and ``status`` of ``available`` or ``matched``).
    - ``feedback``: bounded ``tone``, ``title``, ``message`` and optional
      ``rejected_keepsake_id`` used only for presentation.
    - ``acknowledged_command_id``, ``counts`` and ``can_continue``.

    Commands share the exact envelope ``schema_version``, ``command_id``,
    ``task_id``, ``revision`` and ``action``. ``submit_match`` adds exactly
    ``keepsake_id`` and ``mentor_id``. ``continue_investigation``, ``go_back``,
    ``rename_player``, ``restart_game`` and ``exit_game`` add no fields.
    Python must strictly validate the envelope and owns the matching table.
    """

    clean_task_id = str(task_id).strip()[:120]
    if not clean_task_id:
        raise ValueError("task_id must not be empty")
    clean_revision = int(revision)
    if clean_revision < 0:
        raise ValueError("revision must be non-negative")

    callback = on_command_change or (lambda: None)
    return _CASH_MENTOR_COUNCIL(
        data={
            "schema_version": 1,
            "task_id": clean_task_id,
            "revision": clean_revision,
            "state": dict(state),
        },
        key=key,
        width="stretch",
        height="stretch",
        on_command_change=callback,
    )


__all__ = ["render_cash_mentor_council"]
