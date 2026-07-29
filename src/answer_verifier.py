"""Verify answer and challenge provenance before displaying final status."""

import re
from typing import TypedDict

from src.grounded_answer import GroundedAnswer
from src.report_retriever import SearchResult
from src.skeptical_review import SkepticalReview


class VerificationCheck(TypedDict):
    """One transparent pass/fail condition in the answer audit."""

    name: str
    passed: bool
    detail: str


class VerificationResult(TypedDict):
    """The deterministic decision produced by the verifier."""

    status: str
    summary: str
    checks: list[VerificationCheck]
    limitation: str


WHITESPACE_PATTERN = re.compile(r"\s+")
CHINESE_CHARACTER_PATTERN = re.compile(r"[\u4e00-\u9fff]")


def _normalise_text(text: str) -> str:
    """Normalise PDF whitespace so exact source phrases can be compared."""
    cleaned = text.replace("\xa0", " ").replace("\x07", " ")
    return WHITESPACE_PATTERN.sub(" ", cleaned).strip().lower()


def _source_contains(
    text: str,
    page_number: int,
    sources: list[tuple[int, str]],
) -> bool:
    """Check that a displayed phrase exists in source text on the cited page."""
    comparable_text = _normalise_text(text).rstrip("…")
    return bool(comparable_text) and any(
        source_page == page_number
        and comparable_text in _normalise_text(source_text)
        for source_page, source_text in sources
    )


def _valid_page_number(page_number: object) -> bool:
    """PDF pages must be positive integers, not invented labels."""
    return isinstance(page_number, int) and page_number >= 1


def verify_answer(
    query: str,
    answer: GroundedAnswer,
    skeptical_review: SkepticalReview,
    results: list[SearchResult],
) -> VerificationResult:
    """Audit evidence, citations, and counter-evidence before output approval."""
    if not query.strip():
        raise ValueError("A question is required.")

    answer_sources = [
        (item["page_number"], item["excerpt"])
        for item in answer["evidence"]
    ]
    retrieved_sources = [
        (result["page_number"], result["text"])
        for result in results
    ]
    all_cited_pages = [
        item["page_number"]
        for item in [
            *answer["evidence"],
            *answer["key_points"],
            *skeptical_review["challenges"],
        ]
    ]

    evidence_threshold_passed = (
        answer["is_supported"]
        and bool(answer["evidence"])
        and bool(answer["key_points"])
    )
    answer_traceability_passed = (
        evidence_threshold_passed
        and all(
            _source_contains(
                text=point["text"],
                page_number=point["page_number"],
                sources=answer_sources,
            )
            for point in answer["key_points"]
        )
    )
    citations_passed = bool(all_cited_pages) and all(
        _valid_page_number(page_number)
        for page_number in all_cited_pages
    )

    expected_skeptic_statuses = (
        {"counter_evidence_found", "no_counter_evidence_found"}
        if answer["is_supported"]
        else {"not_applicable"}
    )
    skeptic_consistency_passed = (
        skeptical_review["status"] in expected_skeptic_statuses
        and (
            skeptical_review["status"] != "counter_evidence_found"
            or bool(skeptical_review["challenges"])
        )
        and (
            skeptical_review["status"] == "counter_evidence_found"
            or not skeptical_review["challenges"]
        )
    )
    challenge_traceability_passed = all(
        _source_contains(
            text=challenge["excerpt"],
            page_number=challenge["page_number"],
            sources=retrieved_sources,
        )
        for challenge in skeptical_review["challenges"]
    )

    checks: list[VerificationCheck] = [
        {
            "name": "Evidence threshold / 证据门槛",
            "passed": evidence_threshold_passed,
            "detail": (
                "The answer has sufficient retrieved evidence and at least "
                "one evidence-backed point."
            ),
        },
        {
            "name": "Answer traceability / 结论可追溯",
            "passed": answer_traceability_passed,
            "detail": (
                "Every displayed answer point is present in the cited "
                "source extract on the same PDF page."
            ),
        },
        {
            "name": "PDF citations / 页码检查",
            "passed": citations_passed,
            "detail": "Every displayed citation uses a positive PDF page.",
        },
        {
            "name": "Skeptic consistency / 质疑状态一致",
            "passed": skeptic_consistency_passed,
            "detail": (
                "The Skeptic status agrees with whether counter-evidence "
                "was actually found."
            ),
        },
        {
            "name": "Challenge traceability / 反方证据可追溯",
            "passed": challenge_traceability_passed,
            "detail": (
                "Every displayed challenge is present in retrieved report "
                "text on the cited PDF page."
            ),
        },
    ]

    chinese_query = bool(CHINESE_CHARACTER_PATTERN.search(query))
    if not all(check["passed"] for check in checks):
        status = "rejected"
        summary = (
            "验证结果：拒绝输出。至少一项证据或引用检查未通过。"
            if chinese_query
            else (
                "Verifier result: rejected. At least one evidence or "
                "citation check failed."
            )
        )
    elif skeptical_review["status"] == "counter_evidence_found":
        status = "approved_with_caveats"
        summary = (
            "验证结果：通过，但必须连同反方证据和限制一起展示。"
            if chinese_query
            else (
                "Verifier result: approved with caveats. Counter-evidence "
                "and limitations must remain visible."
            )
        )
    else:
        status = "approved"
        summary = (
            "验证结果：通过当前的证据与引用完整性检查。"
            if chinese_query
            else (
                "Verifier result: approved by the current evidence and "
                "citation-integrity checks."
            )
        )

    return {
        "status": status,
        "summary": summary,
        "checks": checks,
        "limitation": (
            "This deterministic verifier checks provenance and disclosure. "
            "It does not prove that the financial interpretation is complete "
            "or economically correct."
        ),
    }
