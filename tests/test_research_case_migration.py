from copy import deepcopy

import pytest

from src.research_case import MAX_HYPOTHESES, ResearchCaseCapacityError
from src.research_case_migration import migrate_legacy_v3_case


NOW = "2026-08-30T12:00:00+00:00"


def _company(code: str = "600519") -> dict[str, str]:
    return {
        "code": code,
        "canonical_code": f"{code}.SH",
        "name": "贵州茅台",
        "exchange": "SH",
    }


def _thesis(
    thesis_id: str,
    *,
    canonical_code: str = "600519.SH",
) -> dict[str, str]:
    return {
        "canonical_code": canonical_code,
        "thesis_id": thesis_id,
        "hypothesis": f"研究假设{thesis_id}",
        "confirmation_criteria": "经营现金流与收入同步改善",
        "invalidation_criteria": "现金回款连续恶化",
        "topic": "财务与业绩",
        "status": "待核验",
        "created_at": "2026-08-01T10:00:00+00:00",
        "updated_at": "2026-08-02T10:00:00+00:00",
    }


def _migrate(
    legacy: object,
    *,
    existing_case: object = None,
) -> tuple[dict[str, object], list[str]]:
    return migrate_legacy_v3_case(
        legacy,
        company=_company(),
        case_id="case-600519",
        migrated_at=NOW,
        effective_market_date="2026-08-29",
        existing_case=existing_case,
    )


def test_migration_keeps_only_target_checkpoint_and_theses() -> None:
    legacy = {
        "version": 3,
        "recent": [_company("600000")],
        "watchlist": [_company("600000")],
        "evidence_checkpoints": [
            {
                **_company("600000"),
                "evidence_checked_at": "2026-08-10T09:00:00+00:00",
            },
            {
                **_company(),
                "evidence_checked_at": "2026-08-20T09:00:00+00:00",
            },
        ],
        "research_theses": [
            _thesis("target"),
            _thesis("other", canonical_code="600000.SH"),
        ],
    }

    case, warnings = _migrate(legacy)

    assert warnings == []
    assert case["tracking"]["evidence_checked_at"] == (
        "2026-08-20T09:00:00+00:00"
    )
    assert [item["hypothesis_id"] for item in case["hypotheses"]] == [
        "target"
    ]
    assert case["hypotheses"][0]["review_status"] == "confirmed"
    assert case["artifacts"] == []
    assert case["evidence"] == []
    assert case["readiness"] == "draft"


def test_migration_is_idempotent_and_does_not_duplicate_audit() -> None:
    legacy = {
        "version": 3,
        "evidence_checkpoints": [],
        "research_theses": [_thesis("one")],
    }
    once, _ = _migrate(legacy)
    twice, _ = _migrate(legacy, existing_case=once)

    assert twice == once
    assert len(twice["migration_ids"]) == 1
    assert len(twice["audit_log"]) == 1


def test_normalised_hash_is_independent_of_thesis_order() -> None:
    forward, _ = _migrate(
        {
            "version": 3,
            "evidence_checkpoints": [],
            "research_theses": [_thesis("b"), _thesis("a")],
        }
    )
    reverse, _ = _migrate(
        {
            "version": 3,
            "evidence_checkpoints": [],
            "research_theses": [_thesis("a"), _thesis("b")],
        }
    )

    assert forward["migration_ids"] == reverse["migration_ids"]
    assert [item["hypothesis_id"] for item in forward["hypotheses"]] == [
        "a",
        "b",
    ]


@pytest.mark.parametrize("legacy", [None, [], {"version": 2}, {"version": True}])
def test_corrupt_or_non_v3_state_warns_and_builds_empty_case(
    legacy: object,
) -> None:
    case, warnings = _migrate(legacy)

    assert warnings
    assert case["hypotheses"] == []
    assert case["tracking"]["evidence_checked_at"] is None
    assert case["artifacts"] == []
    assert case["readiness"] == "draft"


def test_invalid_matching_thesis_is_ignored_with_warning() -> None:
    bad = _thesis("broken")
    bad["updated_at"] = "not-a-date"

    case, warnings = _migrate(
        {
            "version": 3,
            "evidence_checkpoints": [],
            "research_theses": [bad],
        }
    )

    assert case["hypotheses"] == []
    assert "格式损坏" in warnings[0]


def test_migration_refuses_over_capacity_without_truncation() -> None:
    legacy = {
        "version": 3,
        "evidence_checkpoints": [],
        "research_theses": [
            _thesis(f"thesis-{index}")
            for index in range(MAX_HYPOTHESES + 1)
        ],
    }
    before = deepcopy(legacy)

    with pytest.raises(ResearchCaseCapacityError, match="容量"):
        _migrate(legacy)

    assert legacy == before
