import pytest

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


def test_skeptical_review_finds_cited_offset() -> None:
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
    answer = build_grounded_answer(
        query="经营现金流为什么增长？",
        results=results,
    )

    review = build_skeptical_review(
        query="经营现金流为什么增长？",
        answer=answer,
        results=results,
    )

    assert review["status"] == "counter_evidence_found"
    assert review["challenges"][0]["page_number"] == 29
    assert "partly offset by higher cash capex" in (
        review["challenges"][0]["excerpt"]
    )
    assert review["challenges"][0]["trigger"] == "partly offset by"


def test_skeptical_review_reports_when_no_explicit_challenge_is_found() -> None:
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
    answer = build_grounded_answer(
        query="Why did operating cash flow increase?",
        results=results,
    )

    review = build_skeptical_review(
        query="Why did operating cash flow increase?",
        answer=answer,
        results=results,
    )

    assert review["status"] == "no_counter_evidence_found"
    assert review["challenges"] == []


def test_skeptical_review_matches_complete_words_not_substrings() -> None:
    results = [
        make_result(
            page_number=29,
            text=(
                "Cash capex reflected investments to optimise the "
                "distribution network and improve customer service."
            ),
            matched_terms=["cash", "capital"],
            matched_concepts=["operating cash flow"],
        )
    ]
    answer = build_grounded_answer(
        query="经营现金流",
        results=results,
    )

    review = build_skeptical_review(
        query="经营现金流",
        answer=answer,
        results=results,
    )

    assert review["status"] == "no_counter_evidence_found"
    assert review["challenges"] == []


def test_skeptical_review_rejects_unrelated_risk_sentence() -> None:
    results = [
        make_result(
            page_number=153,
            text=(
                "Cash flow assumptions were included in the valuation. "
                "Risk-free rates are based on government bond rates."
            ),
            matched_terms=["cash", "flow"],
            matched_concepts=["operating cash flow"],
        )
    ]
    answer = build_grounded_answer(
        query="经营现金流为什么增长？",
        results=results,
    )

    review = build_skeptical_review(
        query="经营现金流为什么增长？",
        answer=answer,
        results=results,
    )

    assert review["status"] == "no_counter_evidence_found"
    assert review["challenges"] == []


def test_skeptical_review_does_not_treat_plain_but_as_counter_evidence() -> None:
    results = [
        make_result(
            page_number=219,
            text=(
                "Revenue includes stores that remained open but excludes "
                "stores closed during the year."
            ),
            matched_terms=["revenue"],
            matched_concepts=["revenue and sales"],
        )
    ]
    answer = build_grounded_answer(
        query="What was revenue?",
        results=results,
    )

    review = build_skeptical_review(
        query="What was revenue?",
        answer=answer,
        results=results,
    )

    assert review["status"] == "no_counter_evidence_found"
    assert review["challenges"] == []


def test_skeptical_review_stops_when_original_answer_is_unsupported() -> None:
    results = [
        make_result(
            page_number=7,
            text="The football programme is mentioned in community news.",
            matched_terms=["football"],
            matched_concepts=[],
        )
    ]
    answer = build_grounded_answer(
        query="公司为什么选择这个足球项目？",
        results=results,
    )

    review = build_skeptical_review(
        query="公司为什么选择这个足球项目？",
        answer=answer,
        results=results,
    )

    assert review["status"] == "not_applicable"
    assert review["challenges"] == []


def test_skeptical_review_rejects_invalid_inputs() -> None:
    supported_answer = build_grounded_answer(
        query="revenue",
        results=[
            make_result(
                page_number=1,
                text="Revenue increased while sales growth remained strong.",
                matched_terms=["revenue", "sales"],
                matched_concepts=["revenue and sales"],
            )
        ],
    )

    with pytest.raises(ValueError, match="question is required"):
        build_skeptical_review(
            query="",
            answer=supported_answer,
            results=[],
        )

    with pytest.raises(ValueError, match="max_challenges must be at least 1"):
        build_skeptical_review(
            query="revenue",
            answer=supported_answer,
            results=[],
            max_challenges=0,
        )
