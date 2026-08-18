"""Spatial browser component for the Stage 4 office investigation.

Python remains authoritative: this module receives only the public scene state
and emits short-lived commands.  In particular, an unsearched location never
contains a document ID or a flag that would reveal whether it is a decoy.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import streamlit as st


_STATIC_DIR = Path(__file__).resolve().parent / "static"
_COMPONENT_HTML = """
<main class="office-game" data-component="cash-office-search">
  <p class="office-boot-status" role="status">正在打开失序办公室……</p>
</main>
"""
_COMPONENT_CSS = (_STATIC_DIR / "cash-office-search-game.css").read_text(
    encoding="utf-8"
)
_COMPONENT_JS = (_STATIC_DIR / "cash-office-search-game.js").read_text(
    encoding="utf-8"
)


_CASH_OFFICE_SEARCH = st.components.v2.component(
    name="wfz_cash_office_search",
    html=_COMPONENT_HTML,
    css=_COMPONENT_CSS,
    js=_COMPONENT_JS,
)


def render_cash_office_search(
    *,
    state: Mapping[str, Any],
    question_id: str,
    revision: int,
    key: str = "wfz_cash_office_search",
    on_command_change: Callable[[], None] | None = None,
) -> Any:
    """Render the office scene and return its transient command result.

    Recommended public ``state`` fields are:

    - ``locations``: ``id``, ``label``, ``x``, ``y`` and a server-approved
      ``status`` (``unsearched``, ``collected`` or ``decoy``).  Do not include
      the outcome for an unsearched location.
    - ``discovered_documents``: collected document metadata for the evidence
      bag (``document_id``, ``location``, ``title``, ``document_type``).
    - ``count``, ``required_count`` and ``search_complete``.
    - ``npc``, ``feedback`` and optional ``reveal`` presentation objects.
    - ``keepsake_discovered`` controls whether the hidden ``暗纹放大镜`` is
      still discoverable beneath the inspected crystal award.
    - ``acknowledged_command_id`` so the browser can clear a pending scan.

    Commands use the common envelope ``schema_version``, ``command_id``,
    ``question_id``, ``revision`` and ``action``. ``discover_location`` adds
    one validated ``location_id``. ``finish_search``, ``go_back``,
    ``rename_player``, ``restart_game``, ``exit_game`` and
    ``discover_keepsake`` add nothing. Python must validate every field and
    owns all document/decoy mappings.
    """

    clean_question_id = str(question_id).strip()[:80]
    if not clean_question_id:
        raise ValueError("question_id must not be empty")
    clean_revision = int(revision)
    if clean_revision < 0:
        raise ValueError("revision must be non-negative")

    callback = on_command_change or (lambda: None)
    return _CASH_OFFICE_SEARCH(
        data={
            "schema_version": 1,
            "question_id": clean_question_id,
            "revision": clean_revision,
            "state": dict(state),
        },
        key=key,
        width="stretch",
        height="content",
        on_command_change=callback,
    )


__all__ = ["render_cash_office_search"]
