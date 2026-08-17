import json

from src.cash_game_progress import (
    CASH_GAME_PROGRESS_VERSION,
    browser_cash_game_snapshot_wins,
    build_cash_game_progress_snapshot,
    clear_cash_game_progress_state,
    normalise_cash_game_progress_snapshot,
    restore_cash_game_progress_snapshot,
)


def test_build_snapshot_preserves_complete_game_checkpoint() -> None:
    state: dict[str, object] = {
        "game_player_name": "  北辰  研究员 ",
        "cash_case_stage": "migration",
        "cash_identity_required": False,
        "cash_timing_order_question_id": "cash-timing-1-120-0",
        "cash_timing_order_completed_question_id": "cash-timing-1-120-0",
        "cash_timing_order_ids": [
            "service_completed",
            "customer_accepted",
            "expense_paid",
            "cash_collected",
        ],
        "cash_discovered_document_ids": [
            "contract_clause",
            "signed_acceptance",
        ],
        "cash_game_keepsakes": [
            "blank_access_card",
            "dual_dial_watch",
        ],
        "cash_game_pending_keepsakes": ["brass_timeline_ruler"],
        "cash_game_used_hints": ["blank_access_card"],
        "cash_case_attempt_index": 8,
        "cash_evidence_attempt_index": 4,
        "cash_defense_lives": 2,
        "cash_defense_round_index": 1,
        "cash_defense_attempt_index": 5,
        "cash_case_last_explanation": "利润与现金并非同一时钟。",
        "cash_evidence_explanation": "合同、发票、回单和账龄相互核验。",
        "cash_defense_completed_explanations": [
            "先陈述事实。",
            "再守住边界。",
        ],
        "historical_game_mission_id": (
            "moutai-repurchase-publication-boundary"
        ),
        "historical_prefill_date": "2024-09-18",
        "historical_prefill_context": "《消失的现金》｜开放调查01",
        "historical_game_mission_date_completed": (
            "moutai-repurchase-publication-boundary"
        ),
        "historical_game_mission_answer": "2024-09-21",
        "historical_game_mission_reasoning_attempt": 2,
        "historical_game_mission_reasoning": "证据时钟与行情时钟不同。",
        "temporary_widget_key": object(),
    }

    snapshot = build_cash_game_progress_snapshot(state)

    assert snapshot is not None
    assert snapshot["version"] == CASH_GAME_PROGRESS_VERSION
    assert snapshot["cash_game_progress_revision"] == 0
    assert snapshot["game_player_name"] == "北辰 研究员"
    assert snapshot["cash_case_stage"] == "migration"
    assert snapshot["cash_identity_required"] is False
    assert snapshot["cash_defense_lives"] == 2
    assert snapshot["cash_discovered_document_ids"] == [
        "contract_clause",
        "signed_acceptance",
    ]
    assert snapshot["cash_game_keepsakes"] == [
        "blank_access_card",
        "dual_dial_watch",
    ]
    assert snapshot["cash_game_pending_keepsakes"] == [
        "brass_timeline_ruler"
    ]
    assert snapshot["cash_game_used_hints"] == ["blank_access_card"]
    assert snapshot["cash_timing_order_ids"] == [
        "service_completed",
        "customer_accepted",
        "expense_paid",
        "cash_collected",
    ]
    assert (
        snapshot["cash_timing_order_completed_question_id"]
        == "cash-timing-1-120-0"
    )
    assert snapshot["cash_defense_completed_explanations"] == [
        "先陈述事实。",
        "再守住边界。",
    ]
    assert snapshot["historical_game_mission_answer"] == "2024-09-21"
    assert "temporary_widget_key" not in snapshot
    json.dumps(snapshot, ensure_ascii=False)


def test_snapshot_applies_strict_bounds_and_discards_unsafe_fields() -> None:
    snapshot = normalise_cash_game_progress_snapshot(
        {
            "version": CASH_GAME_PROGRESS_VERSION,
            "game_player_name": "超长调查员代号ABCDEFGHIJK\x00",
            "cash_case_stage": "admin",
            "cash_identity_required": "yes",
            "cash_discovered_document_ids": [
                "contract_clause",
                "../../unsafe",
                "contract_clause",
            ],
            "cash_timing_order_ids": [
                "cash_collected",
                "../../unsafe",
                "cash_collected",
                "service_completed",
            ],
            "cash_game_keepsakes": [
                "dual_dial_watch",
                "../../unsafe",
            ],
            "cash_game_pending_keepsakes": [
                "dual_dial_watch",
                "brass_timeline_ruler",
                "unknown",
            ],
            "cash_game_used_hints": [
                "blank_access_card",
                "dual_dial_watch",
            ],
            "cash_case_attempt_index": 99_999_999,
            "cash_evidence_attempt_index": -12,
            "cash_defense_lives": 100,
            "cash_defense_round_index": 20,
            "cash_defense_attempt_index": True,
            "historical_game_mission_reasoning_attempt": "9",
            "cash_case_last_explanation": "甲" * 5_000,
            "cash_evidence_explanation": {"not": "text"},
            "cash_defense_completed_explanations": [
                "一",
                2,
                "三",
                "四",
                "不会进入",
            ],
            "historical_game_mission_id": "../../unsafe",
            "historical_game_mission_completed": "mission-ok_1",
            "historical_prefill_date": "2024-02-30",
            "historical_game_mission_answer": "2201-01-01",
            "unknown": "discard me",
        }
    )

    assert snapshot is not None
    assert len(snapshot["game_player_name"]) == 12
    assert snapshot["cash_case_stage"] == "briefing"
    assert "cash_identity_required" not in snapshot
    assert snapshot["cash_case_attempt_index"] == 10_000
    assert snapshot["cash_evidence_attempt_index"] == 0
    assert snapshot["cash_defense_lives"] == 3
    assert snapshot["cash_discovered_document_ids"] == ["contract_clause"]
    assert snapshot["cash_timing_order_ids"] == [
        "cash_collected",
        "service_completed",
    ]
    assert snapshot["cash_game_keepsakes"] == ["dual_dial_watch"]
    assert snapshot["cash_game_pending_keepsakes"] == [
        "brass_timeline_ruler"
    ]
    assert snapshot["cash_game_used_hints"] == ["dual_dial_watch"]
    assert snapshot["cash_defense_round_index"] == 2
    assert snapshot["cash_defense_attempt_index"] == 0
    assert snapshot["historical_game_mission_reasoning_attempt"] == 0
    assert len(snapshot["cash_case_last_explanation"]) == 4_000
    assert snapshot["cash_defense_completed_explanations"] == [
        "一",
        "三",
    ]
    assert "cash_evidence_explanation" not in snapshot
    assert "historical_game_mission_id" not in snapshot
    assert snapshot["historical_game_mission_completed"] == "mission-ok_1"
    assert "historical_prefill_date" not in snapshot
    assert "historical_game_mission_answer" not in snapshot
    assert "unknown" not in snapshot


def test_legacy_game_checkpoint_is_not_restored_after_shell_redesign() -> None:
    """Returning testers must see the new in-game identity prologue once."""
    assert normalise_cash_game_progress_snapshot(
        {
            "version": CASH_GAME_PROGRESS_VERSION - 1,
            "game_player_name": "旧版调查员",
            "cash_case_stage": "evidence",
        }
    ) is None


def test_inconsistent_completed_stage_returns_to_recoverable_mission() -> None:
    snapshot = normalise_cash_game_progress_snapshot(
        {
            "version": CASH_GAME_PROGRESS_VERSION,
            "game_player_name": "北辰",
            "cash_case_stage": "migration_completed",
            "cash_game_progress_revision": 123,
        }
    )

    assert snapshot is not None
    assert snapshot["cash_game_progress_revision"] == 123
    assert snapshot["cash_case_stage"] == "migration"


def test_restore_replaces_only_durable_game_state() -> None:
    state: dict[str, object] = {
        "game_player_name": "旧代号",
        "cash_case_stage": "migration_completed",
        "cash_evidence_explanation": "旧的后期解释",
        "historical_game_mission_completed": "old-mission",
        "unrelated_research_page": "保留",
    }
    snapshot = {
        "version": CASH_GAME_PROGRESS_VERSION,
        "game_player_name": "新代号",
        "cash_case_stage": "evidence",
        "cash_discovered_document_ids": ["ar_subledger"],
        "cash_case_attempt_index": 3,
        "cash_evidence_attempt_index": 2,
        "cash_defense_lives": 3,
        "cash_defense_round_index": 0,
        "cash_defense_attempt_index": 0,
        "historical_game_mission_reasoning_attempt": 0,
        "cash_defense_completed_explanations": [],
    }

    restored = restore_cash_game_progress_snapshot(state, snapshot)

    assert restored is True
    assert state["game_player_name"] == "新代号"
    assert state["cash_case_stage"] == "evidence"
    assert state["cash_evidence_attempt_index"] == 2
    assert state["cash_discovered_document_ids"] == ["ar_subledger"]
    assert "cash_evidence_explanation" not in state
    assert "historical_game_mission_completed" not in state
    assert state["unrelated_research_page"] == "保留"


def test_invalid_snapshot_does_not_mutate_state() -> None:
    state: dict[str, object] = {
        "game_player_name": "北辰",
        "cash_case_stage": "defense",
    }
    original = dict(state)

    assert restore_cash_game_progress_snapshot(state, {"stage": "defense"}) is False
    assert restore_cash_game_progress_snapshot(state, "not a mapping") is False
    assert state == original


def test_schema_upgrade_clear_preserves_unrelated_research_state() -> None:
    state: dict[str, object] = {
        "game_player_name": "旧版调查员",
        "cash_case_stage": "evidence",
        "selected_company": {"code": "600519"},
    }

    clear_cash_game_progress_state(state)

    assert "game_player_name" not in state
    assert "cash_case_stage" not in state
    assert state["selected_company"] == {"code": "600519"}


def test_no_snapshot_is_created_before_player_enters_a_name() -> None:
    assert build_cash_game_progress_snapshot({}) is None
    assert build_cash_game_progress_snapshot({"game_player_name": "   "}) is None


def test_newer_browser_checkpoint_replaces_an_older_tab() -> None:
    current = {
        "version": CASH_GAME_PROGRESS_VERSION,
        "game_player_name": "北辰",
        "cash_case_stage": "practice",
        "cash_game_progress_revision": 5,
    }
    browser = {
        **current,
        "cash_case_stage": "investigation",
        "cash_game_progress_revision": 6,
    }

    assert browser_cash_game_snapshot_wins(
        current,
        browser,
        base_revision=5,
    )


def test_first_of_two_equal_revision_tab_writes_wins() -> None:
    stale_tab = {
        "version": CASH_GAME_PROGRESS_VERSION,
        "game_player_name": "北辰",
        "cash_case_stage": "evidence",
        "cash_game_progress_revision": 6,
    }
    stored_by_other_tab = {
        **stale_tab,
        "cash_case_stage": "investigation",
    }

    assert browser_cash_game_snapshot_wins(
        stale_tab,
        stored_by_other_tab,
        base_revision=5,
    )
    assert not browser_cash_game_snapshot_wins(
        stale_tab,
        stored_by_other_tab,
        base_revision=6,
    )


def test_older_browser_checkpoint_never_replaces_newer_current_state() -> None:
    current = {
        "version": CASH_GAME_PROGRESS_VERSION,
        "game_player_name": "北辰",
        "cash_case_stage": "evidence",
        "cash_game_progress_revision": 7,
    }
    browser = {
        **current,
        "cash_case_stage": "investigation",
        "cash_game_progress_revision": 6,
    }

    assert not browser_cash_game_snapshot_wins(
        current,
        browser,
        base_revision=6,
    )
