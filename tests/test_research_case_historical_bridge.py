from copy import deepcopy
from datetime import date
import json

import pytest

from src.research_case import (
    ResearchCaseValidationError,
    apply_case_patch,
    empty_research_case_store,
    new_research_case,
    reduce_research_case_store,
)
from src.research_case_historical_bridge import (
    HISTORICAL_ARTIFACT_PAYLOAD_BYTES,
    build_historical_lens_case_patch,
)


NOW = "2026-08-30T12:00:00+00:00"


def _company() -> dict[str, object]:
    return {
        "code": "600519",
        "canonical_code": "600519.SH",
        "name": "贵州茅台",
        "exchange": "SH",
        "official_domains": ["moutaichina.com"],
    }


def _case(*, historical: bool = False) -> dict[str, object]:
    return new_research_case(
        "case-600519",
        _company(),
        mode="historical" if historical else "current",
        as_of_date="2025-04-10" if historical else None,
        effective_market_date="2025-04-10" if historical else "2026-08-29",
        created_at=NOW,
    )


def _snapshot(**updates: object) -> dict[str, object]:
    snapshot: dict[str, object] = {
        "requested_date": "2025-04-10",
        "effective_market_date": "2025-04-10",
        "latest_close": 1520.5,
        "volume": 1_234_567.0,
        "turnover": 0.0075,
        "return_20d": 0.03,
        "return_60d": -0.02,
        "return_250d": 0.12,
        "annualised_volatility": 0.24,
        "max_drawdown": -0.16,
        "observations": 251,
        "source": "腾讯财经公开日线（备用源）",
        "adjustment": "不复权",
    }
    snapshot.update(updates)
    return snapshot


def _record(
    source_id: str,
    published_date: str,
    *,
    url: str | None = None,
    page_number: int | None = None,
) -> dict[str, object]:
    return {
        "source_id": source_id,
        "source_type": "年度报告",
        "title": f"公告{source_id}",
        "published_date": published_date,
        "period_end": None,
        "source_url": url or f"https://static.cninfo.com.cn/{source_id}.pdf",
        "page_number": page_number,
        "evidence_grade": "A",
        "verification_status": "verified",
    }


def _evidence_result(*records: dict[str, object]) -> dict[str, object]:
    return {
        "as_of_date": "2025-04-10",
        "accepted": list(records),
        "excluded": [],
        "input_count": len(records),
        "accepted_count": len(records),
        "excluded_count": 0,
    }


def _patch(
    case: dict[str, object],
    *,
    snapshot: dict[str, object] | None = None,
    evidence_result: object = None,
    patch_id: str = "historical-bridge-1",
    emitted_at: str = NOW,
) -> dict[str, object]:
    return build_historical_lens_case_patch(
        case,
        snapshot or _snapshot(),
        evidence_result,
        patch_id=patch_id,
        emitted_at=emitted_at,
    )


def test_official_pre_cutoff_evidence_produces_reducer_applicable_patch() -> None:
    case = _case(historical=True)
    case_before = deepcopy(case)
    evidence_result = _evidence_result(
        _record("report", "2025-04-09", page_number=18)
    )
    patch = _patch(case, evidence_result=evidence_result)

    assert patch["source_module"] == "historical_lens"
    assert patch["question_updates"]["point_in_time"]["status"] == "answered"
    assert patch["evidence"][0]["source_tier"] == "official_disclosure"
    assert patch["evidence"][0]["published_date"] == "2025-04-09"
    assert patch["evidence"][0]["page_start"] == 18
    assert "tracking" not in patch

    store = empty_research_case_store()
    store["cases"][case["case_id"]] = case
    store["active_case_id"] = case["case_id"]
    reduced = reduce_research_case_store(
        store,
        {
            "command_id": "apply-historical-1",
            "base_store_revision": 0,
            "action": "apply_patch",
            "emitted_at": NOW,
            "patch": patch,
        },
    )
    applied = reduced["cases"][case["case_id"]]
    assert applied["questions"]["point_in_time"]["evidence_ids"] == [
        patch["evidence"][0]["evidence_id"]
    ]
    assert applied["tracking"]["evidence_checked_at"] is None
    assert case == case_before


def test_exact_retry_is_content_addressed_and_fully_idempotent() -> None:
    case = _case(historical=True)
    previous_evidence_check = "2026-08-29T09:00:00+00:00"
    case["tracking"]["evidence_checked_at"] = previous_evidence_check
    evidence_result = _evidence_result(
        _record("report", "2025-04-09", page_number=18)
    )

    first = _patch(
        case,
        evidence_result=evidence_result,
        patch_id="ui-random-request-one",
        emitted_at="2026-08-30T12:00:00+00:00",
    )
    once = apply_case_patch(case, first)
    once_summary = once["case_brief"]["evidence"]["summary"]
    once_audit_count = len(once["audit_log"])
    once_revision = once["revision"]

    replay = _patch(
        once,
        evidence_result=evidence_result,
        patch_id="ui-random-request-two",
        emitted_at="2026-08-30T13:00:00+00:00",
    )
    twice = apply_case_patch(once, replay)

    assert replay["patch_id"] == first["patch_id"]
    assert replay["patch_id"].startswith("patch-historical-")
    assert twice == once
    assert twice["revision"] == once_revision
    assert len(twice["audit_log"]) == once_audit_count
    assert twice["case_brief"]["evidence"]["summary"] == once_summary
    assert (
        twice["tracking"]["evidence_checked_at"]
        == previous_evidence_check
    )


def test_content_address_changes_when_historical_snapshot_changes() -> None:
    case = _case(historical=True)
    evidence_result = _evidence_result(_record("report", "2025-04-09"))

    first = _patch(case, evidence_result=evidence_result)
    changed = _patch(
        case,
        snapshot=_snapshot(latest_close=1521.5),
        evidence_result=evidence_result,
        patch_id="another-request-label",
    )

    assert changed["patch_id"] != first["patch_id"]


def test_page_date_objects_are_normalised_before_v1_validation() -> None:
    record = _record("date-object", "2025-04-09")
    record["published_date"] = date(2025, 4, 9)

    patch = _patch(_case(), evidence_result=_evidence_result(record))

    assert patch["evidence"][0]["published_date"] == "2025-04-09"


def test_no_official_evidence_keeps_point_in_time_blocked() -> None:
    patch = _patch(_case(), evidence_result=None)

    point_in_time = patch["question_updates"]["point_in_time"]
    assert point_in_time["status"] == "blocked"
    assert point_in_time["evidence_ids"] == []
    assert "官方原文" in point_in_time["next_action"]
    assert patch["case_brief_update"]["next_action"]["module"] == "historical_lens"


def test_future_and_invalid_evidence_are_not_persisted_or_referenced() -> None:
    future_url = "https://static.cninfo.com.cn/future-secret.pdf"
    invalid_url = "https://example.com/fake.pdf"
    patch = _patch(
        _case(),
        evidence_result=_evidence_result(
            _record("future-title", "2025-04-11", url=future_url),
            _record("invalid-title", "2025-04-09", url=invalid_url),
        ),
    )

    serialised = json.dumps(patch, ensure_ascii=False)
    assert patch["evidence"] == []
    assert patch["question_updates"]["point_in_time"]["status"] == "blocked"
    assert "future-title" not in serialised
    assert future_url not in serialised
    assert "invalid-title" not in serialised
    assert invalid_url not in serialised


def test_later_reveal_fields_are_never_copied_into_artifact() -> None:
    snapshot = _snapshot(
        later_outcomes=[
            {
                "outcome_date": "2025-10-10",
                "return_since_base": 9.99,
                "secret": "未来揭晓内容",
            }
        ],
        outcome_close=9999,
    )
    evidence_result = _evidence_result(_record("known", "2025-04-09"))
    evidence_result["later_reveal"] = "后来涨跌"
    patch = _patch(
        _case(), snapshot=snapshot, evidence_result=evidence_result
    )

    payload = patch["artifact"]["payload"]
    serialised = json.dumps(payload, ensure_ascii=False)
    assert "outcome_date" not in serialised
    assert "return_since_base" not in serialised
    assert "未来揭晓内容" not in serialised
    assert "后来涨跌" not in serialised
    assert payload["controls"]["later_outcomes_included"] is False


def test_artifact_is_under_four_kb_even_with_untrusted_large_extras() -> None:
    class MustNotStringify:
        def __str__(self) -> str:
            raise AssertionError("bridge must ignore arbitrary objects")

    snapshot = _snapshot(raw_frame=MustNotStringify(), chart=MustNotStringify())
    record = _record("known", "2025-04-09")
    record["full_pdf"] = MustNotStringify()
    patch = _patch(
        _case(),
        snapshot=snapshot,
        evidence_result=_evidence_result(record),
    )
    payload = patch["artifact"]["payload"]
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    assert len(encoded) <= HISTORICAL_ARTIFACT_PAYLOAD_BYTES
    assert "raw_frame" not in encoded.decode("utf-8")
    assert "chart" not in encoded.decode("utf-8")
    assert "full_pdf" not in encoded.decode("utf-8")


def test_historical_case_rejects_mismatched_cutoff_or_market_date() -> None:
    case = _case(historical=True)
    with pytest.raises(ResearchCaseValidationError, match="截止日不一致"):
        _patch(
            case,
            snapshot=_snapshot(
                requested_date="2025-04-09",
                effective_market_date="2025-04-09",
            ),
        )
    with pytest.raises(ResearchCaseValidationError, match="交易日与历史案件"):
        _patch(case, snapshot=_snapshot(effective_market_date="2025-04-09"))


def test_official_evidence_is_rechecked_even_if_upstream_marks_it_accepted() -> None:
    unverified = _record("candidate", "2025-04-09")
    unverified["verification_status"] = "candidate"
    low_grade = _record("grade-b", "2025-04-09")
    low_grade["evidence_grade"] = "B"

    patch = _patch(
        _case(), evidence_result=_evidence_result(unverified, low_grade)
    )

    assert patch["evidence"] == []
    assert patch["artifact"]["payload"]["rejected_evidence_count"] == 2
    assert patch["question_updates"]["point_in_time"]["status"] == "blocked"
