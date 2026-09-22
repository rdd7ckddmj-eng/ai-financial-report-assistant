from __future__ import annotations

from copy import deepcopy
import json

import pytest

from src.agent_coordinator import run_agent_workflow
from src.agent_router import route_question
from src.research_case import (
    ResearchCaseValidationError,
    apply_case_patch,
    new_research_case,
)
from src.research_case_annual_report_qa_bridge import (
    ANNUAL_QA_ARTIFACT_PAYLOAD_BYTES,
    build_annual_report_qa_case_patch,
)


QUESTION = "为什么经营现金流增加？"
REPORT_NAME = "测试公司2025年年度报告.pdf"
SOURCE_URL = "https://static.cninfo.com.cn/finalpage/test-2025.PDF"
FINGERPRINT = "a" * 64
EMITTED_AT = "2026-08-30T16:00:00+00:00"


def _company() -> dict[str, str]:
    return {
        "code": "600000",
        "canonical_code": "600000.SH",
        "name": "测试公司",
        "exchange": "SH",
    }


def _case(
    *,
    historical: bool = False,
    as_of_date: str = "2026-04-30",
) -> dict[str, object]:
    return new_research_case(
        "case-annual-qa",
        _company(),
        mode="historical" if historical else "current",
        as_of_date=as_of_date if historical else None,
        effective_market_date=as_of_date if historical else "2026-08-29",
        created_at="2026-08-30T10:00:00+00:00",
    )


def _verified_run(
    *, with_challenge: bool = True
) -> tuple[dict[str, object], dict[str, object]]:
    route = route_question(QUESTION)
    chunks = [
        {
            "page_number": 12,
            "chunk_index": 0,
            "text": (
                "Operating cash flow increased because working capital "
                "improved and customer cash receipts increased."
                + (
                    " However, operating cash flow remained exposed to "
                    "seasonal inventory movements and uncertain supplier timing."
                    if with_challenge
                    else ""
                )
            ),
        },
        {
            "page_number": 13,
            "chunk_index": 0,
            "text": (
                "The company generated strong operating cash flow, supported "
                "by higher cash collections and disciplined working capital."
            ),
        },
    ]
    final_run = run_agent_workflow(
        query=QUESTION,
        chunks=chunks,
        route=route,
    )
    assert final_run["verification"] is not None
    assert final_run["verification"]["status"] in {
        "approved",
        "approved_with_caveats",
    }
    answer = final_run["answer"]
    skeptic = final_run["skeptical_review"]
    pages = {
        item["page_number"] for item in answer["evidence"]  # type: ignore[index]
    }
    pages.update(
        item["page_number"] for item in skeptic["challenges"]  # type: ignore[index]
    )
    audit = {
        "schema_version": "1.0",
        "report_name": REPORT_NAME,
        "query": QUESTION,
        "answer": final_run["answer"],
        "skeptical_review": final_run["skeptical_review"],
        "verification": final_run["verification"],
        "cited_pdf_pages": sorted(pages),
        "final_agent_trace": final_run["trace"],
    }
    return final_run, audit


def _patch(
    case: dict[str, object],
    *,
    final_run: object | None = None,
    audit: object | None = None,
    published_date: str = "2026-04-20",
) -> dict[str, object]:
    if final_run is None or audit is None:
        default_run, default_audit = _verified_run()
        final_run = default_run if final_run is None else final_run
        audit = default_audit if audit is None else audit
    return build_annual_report_qa_case_patch(
        case,
        report_name=REPORT_NAME,
        source_url=SOURCE_URL,
        source_fingerprint_sha256=FINGERPRINT,
        report_published_date=published_date,
        question=QUESTION,
        final_run=final_run,
        audit_record=audit,
        emitted_at=EMITTED_AT,
    )


def test_verified_qa_becomes_page_linked_source_records_not_ai_facts() -> None:
    case = _case()
    before = deepcopy(case)

    patch = _patch(case)
    applied = apply_case_patch(case, patch)

    assert case == before
    assert patch["source_module"] == "annual_report"
    assert patch["artifact"]["review_status"] == "not_required"
    assert patch["evidence"]
    assert {
        item["review_status"] for item in patch["evidence"]
    } == {"not_required"}
    assert all(item["page_start"] >= 1 for item in patch["evidence"])
    assert all(item["page_start"] == item["page_end"] for item in patch["evidence"])
    assert all(item["source_url"] == SOURCE_URL for item in patch["evidence"])
    assert all(item["excerpt"] for item in patch["evidence"])
    assert (
        patch["question_updates"]["financial_quality"]["status"]
        in {"answered", "in_progress"}
    )
    assert applied["readiness"] == "in_progress"
    assert applied["case_brief"]["unknowns"] == []
    payload = patch["artifact"]["payload"]
    assert payload["report"]["source_fingerprint_sha256"] == FINGERPRINT
    assert payload["question"] == QUESTION
    assert payload["analysis_output"]["conclusion"]
    assert payload["controls"] == {
        "verifier_passed": True,
        "page_citations_required": True,
        "analysis_output_is_fact": False,
        "evidence_contains_generated_claim": False,
        "source_pdf_embedded": False,
        "retrieval_chunks_embedded": False,
    }
    assert all(
        "结论" not in item["excerpt"] for item in patch["evidence"]
    )
    conclusion = payload["analysis_output"]["conclusion"]
    non_analysis_surface = {
        "evidence": patch["evidence"],
        "case_brief_update": patch["case_brief_update"],
        "question_updates": patch["question_updates"],
    }
    assert conclusion not in json.dumps(non_analysis_surface, ensure_ascii=False)
    assert (
        len(
            json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        <= ANNUAL_QA_ARTIFACT_PAYLOAD_BYTES
    )


def test_counter_evidence_is_preserved_as_source_record_contradiction() -> None:
    patch = _patch(_case())
    challenges = patch["artifact"]["payload"]["workflow"][
        "challenge_evidence_ids"
    ]
    assert challenges
    contradiction = patch["case_brief_update"]["contradictions"][-1]
    assert set(challenges).issubset(contradiction["evidence_ids"])
    assert "相互约束" in contradiction["summary"]


def test_approved_run_without_caveats_answers_lane_without_review_gate() -> None:
    final_run, audit = _verified_run(with_challenge=False)
    patch = _patch(_case(), final_run=final_run, audit=audit)

    assert patch["artifact"]["payload"]["workflow"]["challenge_evidence_ids"] == []
    assert patch["question_updates"]["financial_quality"]["status"] == "answered"
    assert patch["artifact"]["review_status"] == "not_required"
    assert all(item["review_status"] == "not_required" for item in patch["evidence"])


def test_annual_qa_does_not_advance_disclosure_tracking_checkpoint() -> None:
    case = _case()
    case["tracking"]["evidence_checked_at"] = "2026-08-29T09:00:00+00:00"

    patch = _patch(case)
    applied = apply_case_patch(case, patch)

    assert "tracking" not in patch
    assert applied["tracking"] == {
        "evidence_checked_at": "2026-08-29T09:00:00+00:00"
    }


def test_insufficient_or_tampered_verification_writes_nothing() -> None:
    case = _case()
    before = deepcopy(case)
    final_run, audit = _verified_run()
    final_run["results"] = []

    with pytest.raises(ResearchCaseValidationError, match="没有可核验"):
        _patch(case, final_run=final_run, audit=audit)
    assert case == before

    final_run, audit = _verified_run()
    final_run["answer"]["evidence"][0]["excerpt"] = "原文中不存在的伪造摘录"
    audit["answer"] = final_run["answer"]
    with pytest.raises(
        ResearchCaseValidationError, match="Verifier|引用复核|同页"
    ):
        _patch(case, final_run=final_run, audit=audit)
    assert case == before


def test_missing_or_invalid_page_cannot_be_persisted() -> None:
    final_run, audit = _verified_run()
    final_run["answer"]["evidence"][0]["page_number"] = 0
    final_run["answer"]["key_points"][0]["page_number"] = 0
    audit["answer"] = final_run["answer"]
    audit["cited_pdf_pages"] = [0]

    with pytest.raises(
        ResearchCaseValidationError, match="Verifier|引用复核|正整数"
    ):
        _patch(_case(), final_run=final_run, audit=audit)


def test_historical_cutoff_and_official_source_are_enforced() -> None:
    with pytest.raises(ResearchCaseValidationError, match="截止日之后"):
        _patch(
            _case(historical=True, as_of_date="2025-12-31"),
            published_date="2026-04-20",
        )

    final_run, audit = _verified_run()
    with pytest.raises(ResearchCaseValidationError, match="官方披露"):
        build_annual_report_qa_case_patch(
            _case(),
            report_name=REPORT_NAME,
            source_url="https://example.com/not-official.pdf",
            source_fingerprint_sha256=FINGERPRINT,
            report_published_date="2026-04-20",
            question=QUESTION,
            final_run=final_run,
            audit_record=audit,
            emitted_at=EMITTED_AT,
        )


def test_binary_is_rejected_and_large_chunks_are_never_copied() -> None:
    final_run, audit = _verified_run()
    final_run["pdf_bytes"] = b"%PDF-secret"
    with pytest.raises(ResearchCaseValidationError, match="不得包含PDF"):
        _patch(_case(), final_run=final_run, audit=audit)

    final_run, audit = _verified_run()
    marker = "RAW-CHUNK-MUST-NOT-PERSIST-" + "X" * 200_000
    final_run["results"][0]["raw_full_page"] = marker
    patch = _patch(_case(), final_run=final_run, audit=audit)
    serialised = json.dumps(patch, ensure_ascii=False)
    assert "RAW-CHUNK-MUST-NOT-PERSIST" not in serialised
    assert len(
        json.dumps(
            patch["artifact"]["payload"],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ) <= ANNUAL_QA_ARTIFACT_PAYLOAD_BYTES


def test_deterministic_patch_id_is_idempotent_after_first_application() -> None:
    case = _case()
    final_run, audit = _verified_run()
    first_patch = _patch(case, final_run=final_run, audit=audit)
    once = apply_case_patch(case, first_patch)

    replay_patch = _patch(once, final_run=final_run, audit=audit)
    twice = apply_case_patch(once, replay_patch)

    assert replay_patch["patch_id"] == first_patch["patch_id"]
    assert replay_patch["artifact"]["artifact_id"] == first_patch["artifact"]["artifact_id"]
    assert twice == once
    assert twice["revision"] == 1
