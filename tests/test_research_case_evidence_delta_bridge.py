from copy import deepcopy
from datetime import date
import json

import pytest

from src.china_stock import build_company_identity
from src.evidence_delta import (
    build_evidence_delta_review,
    build_evidence_window,
)
from src.research_case import (
    MAX_EVIDENCE,
    ResearchCaseValidationError,
    apply_case_patch,
    new_research_case,
    validate_research_case,
)
from src.research_case_evidence_delta_bridge import (
    EVIDENCE_DELTA_ARTIFACT_PAYLOAD_BYTES,
    MAX_EVIDENCE_DELTA_EVIDENCE_PER_PATCH,
    build_evidence_delta_research_case_patch,
)


NOW = "2026-08-31T12:00:00+00:00"


def _company(code: str = "600519", name: str = "贵州茅台") -> dict[str, str]:
    return build_company_identity(code, name)


def _case(*, historical: bool = False) -> dict[str, object]:
    return new_research_case(
        "case-600519",
        _company(),
        mode="historical" if historical else "current",
        as_of_date="2026-08-20" if historical else None,
        effective_market_date="2026-08-20" if historical else "2026-08-30",
        created_at="2026-08-30T10:00:00+00:00",
    )


def _announcement(
    title: str,
    published_date: date,
    *,
    category: str = "经营动态",
    attention: str = "中",
    url: str = "https://static.cninfo.com.cn/finalpage/test.PDF",
) -> dict[str, object]:
    return {
        "title": title,
        "date": published_date,
        "url": url,
        "category": category,
        "attention": attention,
    }


def _review(
    *announcements: dict[str, object],
    company: dict[str, str] | None = None,
    checkpoint: str | None = None,
) -> dict[str, object]:
    company = company or _company()
    window = build_evidence_window(
        checkpoint,
        as_of_date=date(2026, 8, 31),
    )
    return build_evidence_delta_review(
        company,
        list(announcements),
        window=window,
        generated_on=date(2026, 8, 31),
    )


def _patch(
    case: dict[str, object],
    review: dict[str, object],
    *,
    emitted_at: str = NOW,
) -> dict[str, object]:
    return build_evidence_delta_research_case_patch(
        case,
        review,
        emitted_at=emitted_at,
    )


def test_official_delta_updates_recent_events_without_directional_judgement() -> None:
    case = _case()
    review = _review(
        _announcement(
            "2026年半年度报告",
            date(2026, 8, 30),
            category="财务报告",
            attention="高",
        )
    )
    case_before = deepcopy(case)
    review_before = deepcopy(review)

    patch = _patch(case, review)

    assert patch["source_module"] == "evidence_delta"
    assert patch["canonical_code"] == "600519.SH"
    assert patch["question_updates"]["recent_events"]["status"] == "in_progress"
    assert patch["evidence"][0]["source_tier"] == "official_disclosure"
    assert patch["evidence"][0]["title"] == "2026年半年度报告"
    assert patch["evidence"][0]["published_date"] == "2026-08-30"
    assert patch["evidence"][0]["source_url"].startswith(
        "https://static.cninfo.com.cn/"
    )
    assert "关注程度：高" in patch["evidence"][0]["basis"]
    assert "不代表利好、利空或价格方向" in patch["evidence"][0]["basis"]
    payload = patch["artifact"]["payload"]
    assert payload["official_references"][0] == {
        "evidence_id": patch["evidence"][0]["evidence_id"],
        "source_category": "财务报告",
        "evidence_group": "财务与业绩",
        "attention": "高",
        "delta_status": "首次基准",
    }
    assert payload["controls"]["attention_is_directional_judgement"] is False
    assert "contradictions" not in patch["case_brief_update"]

    applied = apply_case_patch(case, patch)
    validate_research_case(applied)
    assert applied["questions"]["recent_events"]["evidence_ids"] == [
        patch["evidence"][0]["evidence_id"]
    ]
    assert applied["tracking"]["evidence_checked_at"] == (
        "2026-08-31T00:00:00+00:00"
    )
    assert case == case_before
    assert review == review_before


def test_patch_id_is_deterministic_and_exact_replay_is_idempotent() -> None:
    case = _case()
    review = _review(
        _announcement("董事会决议公告", date(2026, 8, 30))
    )

    first = _patch(case, review, emitted_at="2026-08-31T12:00:00+00:00")
    second = _patch(case, review, emitted_at="2026-08-31T13:00:00+00:00")

    assert first["patch_id"] == second["patch_id"]
    once = apply_case_patch(case, first)
    twice = apply_case_patch(once, first)
    assert twice == once


def test_company_mismatch_and_historical_case_are_rejected() -> None:
    mismatch = _review(
        _announcement("公告", date(2026, 8, 30)),
        company=_company("000858", "五粮液"),
    )
    with pytest.raises(ResearchCaseValidationError, match="公司不匹配"):
        _patch(_case(), mismatch)

    with pytest.raises(ResearchCaseValidationError, match="Historical Lens"):
        _patch(_case(historical=True), _review())


def test_invalid_or_future_sources_are_not_copied_or_referenced() -> None:
    review = _review()
    review["items"] = [
        {
            "title": "不可信公告",
            "published_date": date(2026, 8, 30),
            "source_url": "https://example.com/private.pdf",
            "source_category": "经营动态",
            "evidence_group": "经营事项",
            "attention": "高",
            "delta_status": "首次基准",
            "raw_html": "绝不应保存的正文",
        },
        {
            "title": "未来公告",
            "published_date": date(2026, 9, 1),
            "source_url": "https://static.cninfo.com.cn/future.pdf",
            "source_category": "经营动态",
            "evidence_group": "经营事项",
            "attention": "高",
            "delta_status": "首次基准",
        },
        {
            "title": "超长链接公告",
            "published_date": date(2026, 8, 30),
            "source_url": "https://static.cninfo.com.cn/" + "z" * 900,
            "source_category": "经营动态",
            "evidence_group": "经营事项",
            "attention": "中",
            "delta_status": "首次基准",
        },
    ]

    patch = _patch(_case(), review)
    serialised = json.dumps(patch, ensure_ascii=False)

    assert patch["evidence"] == []
    assert patch["question_updates"]["recent_events"]["status"] == "blocked"
    assert "https://example.com" not in serialised
    assert "绝不应保存的正文" not in serialised
    assert "future.pdf" not in serialised
    assert "超长链接公告" not in serialised


def test_empty_first_run_writes_control_artifact_and_explicit_unknown() -> None:
    patch = _patch(_case(), _review())

    assert patch["evidence"] == []
    assert patch["artifact"]["payload"]["counts"]["written_to_case"] == 0
    assert patch["question_updates"]["recent_events"]["status"] == "blocked"
    assert "不能证明期间没有公告" in patch["question_updates"]["recent_events"][
        "summary"
    ]
    assert "unknowns" in patch["case_brief_update"]
    assert "tracking" not in patch
    applied = apply_case_patch(_case(), patch)
    assert len(applied["artifacts"]) == 1
    assert applied["evidence"] == []


def test_same_day_item_keeps_same_day_review_semantics() -> None:
    case = _case()
    case["tracking"]["evidence_checked_at"] = "2026-08-30T09:00:00+00:00"
    validate_research_case(case)
    review = _review(
        _announcement("同日补充公告", date(2026, 8, 30)),
        checkpoint="2026-08-30T09:00:00+00:00",
    )
    review["items"][0]["delta_status"] = "新增"  # Untrusted promotion attempt.

    patch = _patch(case, review)

    assert patch["artifact"]["payload"]["official_references"][0][
        "delta_status"
    ] == "同日待复核"
    assert "同日待复核" in patch["evidence"][0]["basis"]


def test_case_checkpoint_must_match_review_baseline() -> None:
    case = _case()
    case["tracking"]["evidence_checked_at"] = "2026-08-29T09:00:00+00:00"
    validate_research_case(case)

    with pytest.raises(ResearchCaseValidationError, match="检查点不一致"):
        _patch(case, _review())


def test_evidence_selection_respects_remaining_case_capacity() -> None:
    case = _case()
    for index in range(MAX_EVIDENCE - 1):
        case["evidence"].append(
            {
                "evidence_id": f"existing-{index}",
                "source_module": "evidence_delta",
                "source_tier": "official_disclosure",
                "title": f"既有公告{index}",
                "source_url": f"https://static.cninfo.com.cn/existing-{index}.pdf",
                "published_date": "2026-08-01",
                "review_status": "not_required",
            }
        )
    validate_research_case(case)
    announcements = [
        _announcement(
            f"新增公告{index}",
            date(2026, 8, 30),
            url=f"https://static.cninfo.com.cn/new-{index}.pdf",
        )
        for index in range(5)
    ]

    patch = _patch(case, _review(*announcements))
    applied = apply_case_patch(case, patch)

    assert len(patch["evidence"]) == 1
    assert patch["artifact"]["payload"]["counts"]["omitted_by_case_limit"] == 4
    assert len(applied["evidence"]) == MAX_EVIDENCE


def test_payload_is_bounded_and_never_copies_binary_or_large_extras() -> None:
    class MustNotStringify:
        def __str__(self) -> str:
            raise AssertionError("bridge must ignore arbitrary large objects")

    review = _review()
    review["pdf_bytes"] = MustNotStringify()
    review["items"] = [
        {
            "title": f"公告{index}" + "长标题" * 150,
            "published_date": date(2026, 8, 30),
            "source_url": (
                f"https://static.cninfo.com.cn/finalpage/{index}.pdf?token="
                + "x" * 600
            ),
            "source_category": "经营动态",
            "evidence_group": "经营事项",
            "attention": "中",
            "delta_status": "首次基准",
            "pdf": MustNotStringify(),
            "raw_response": MustNotStringify(),
        }
        for index in range(100)
    ]
    review["item_limit_reached"] = True

    patch = _patch(_case(), review)
    payload = patch["artifact"]["payload"]
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    serialised = json.dumps(patch, ensure_ascii=False)

    assert len(encoded) <= EVIDENCE_DELTA_ARTIFACT_PAYLOAD_BYTES
    assert len(patch["evidence"]) == MAX_EVIDENCE_DELTA_EVIDENCE_PER_PATCH
    assert "raw_response" not in serialised
    assert "pdf_bytes" not in serialised
    assert payload["controls"]["binary_or_full_response_stored"] is False
