import pytest

from src.answer_verifier import verify_answer
from src.grounded_answer import build_grounded_answer
from src.report_retriever import SearchResult
from src.skeptical_review import build_skeptical_review


def make_result(
    page_number: int,
    text: str,
    matched_terms: list[str],
    matched_concepts: list[str],
) -> SearchResult:
    return {
        "page_number": page_number,
        "chunk_index": 1,
        "text": text,
        "score": 10.0,
        "matched_terms": matched_terms,
        "matched_concepts": matched_concepts,
    }


def build_review_package(
    query: str,
    results: list[SearchResult],
):
    answer = build_grounded_answer(query=query, results=results)
    review = build_skeptical_review(
        query=query,
        answer=answer,
        results=results,
    )
    return answer, review


def test_verifier_approves_supported_answer_with_caveats() -> None:
    query = "经营现金流为什么增长？"
    results = [
        make_result(
            page_number=29,
            text=(
                "Cash generated from operations improved because of working "
                "capital inflows. Free cash flow increased, with the benefit "
                "partly offset by higher cash capex and tax payments."
            ),
            matched_terms=["cash", "generated", "working", "capital"],
            matched_concepts=["operating cash flow"],
        )
    ]
    answer, review = build_review_package(query, results)

    verification = verify_answer(query, answer, review, results)

    assert verification["status"] == "approved_with_caveats"
    assert all(check["passed"] for check in verification["checks"])
    assert "必须连同反方证据" in verification["summary"]


def test_verifier_approves_traceable_answer_without_explicit_challenge() -> None:
    query = "Why did operating cash flow increase?"
    results = [
        make_result(
            page_number=19,
            text=(
                "Operating cash flow increased because working capital "
                "management improved."
            ),
            matched_terms=["operating", "cash", "flow"],
            matched_concepts=["operating cash flow"],
        )
    ]
    answer, review = build_review_package(query, results)

    verification = verify_answer(query, answer, review, results)

    assert verification["status"] == "approved"
    assert all(check["passed"] for check in verification["checks"])


def test_verifier_rejects_unsupported_answer() -> None:
    query = "公司为什么选择这个足球项目？"
    results = [
        make_result(
            page_number=7,
            text="The football programme is mentioned in community news.",
            matched_terms=["football"],
            matched_concepts=[],
        )
    ]
    answer, review = build_review_package(query, results)

    verification = verify_answer(query, answer, review, results)

    assert verification["status"] == "rejected"
    assert verification["checks"][0]["passed"] is False


def test_verifier_rejects_an_invented_answer_point() -> None:
    query = "Why did operating cash flow increase?"
    results = [
        make_result(
            page_number=19,
            text=(
                "Operating cash flow increased because working capital "
                "management improved."
            ),
            matched_terms=["operating", "cash", "flow"],
            matched_concepts=["operating cash flow"],
        )
    ]
    answer, review = build_review_package(query, results)
    answer["key_points"][0]["text"] = "An invented driver not in the report"

    verification = verify_answer(query, answer, review, results)

    assert verification["status"] == "rejected"
    traceability_check = next(
        check
        for check in verification["checks"]
        if check["name"].startswith("Answer traceability")
    )
    assert traceability_check["passed"] is False


def test_verifier_rejects_empty_question() -> None:
    results = [
        make_result(
            page_number=1,
            text="Revenue and sales increased during the year.",
            matched_terms=["revenue", "sales"],
            matched_concepts=["revenue and sales"],
        )
    ]
    answer, review = build_review_package("revenue", results)

    with pytest.raises(ValueError, match="question is required"):
        verify_answer("", answer, review, results)
