import pytest

from src.grounded_answer import build_grounded_answer
from src.report_retriever import SearchResult


def make_result(
    page_number: int,
    text: str,
    matched_terms: list[str],
    matched_concepts: list[str],
    chunk_index: int = 1,
) -> SearchResult:
    return {
        "page_number": page_number,
        "chunk_index": chunk_index,
        "text": text,
        "score": 10.0,
        "matched_terms": matched_terms,
        "matched_concepts": matched_concepts,
    }


def test_build_grounded_answer_uses_source_text_and_page_citations() -> None:
    results = [
        make_result(
            page_number=179,
            text=(
                "The Group maintains committed bank facilities to meet "
                "liquidity needs. There is a risk that cash will not be "
                "available to settle liabilities when they fall due."
            ),
            matched_terms=["cash", "liabilities", "liquidity"],
            matched_concepts=["liquidity"],
        ),
        make_result(
            page_number=125,
            text=(
                "Current assets were lower than current liabilities on the "
                "reporting date."
            ),
            matched_terms=["current", "assets", "liabilities"],
            matched_concepts=["liquidity"],
        ),
    ]

    grounded = build_grounded_answer(
        query="Can the company cover its short-term obligations?",
        results=results,
    )

    assert grounded["is_supported"] is True
    assert "PDF page 179" in grounded["answer"]
    assert "PDF page 125" in grounded["answer"]
    assert grounded["concepts"] == ["liquidity"]
    assert grounded["evidence"][0]["excerpt"] in results[0]["text"]
    assert "not investment advice" in grounded["limitation"]


def test_build_grounded_answer_uses_chinese_introduction() -> None:
    results = [
        make_result(
            page_number=19,
            text=(
                "Operating cash flow increased because cash generation "
                "improved."
            ),
            matched_terms=["operating", "cash", "flow"],
            matched_concepts=["operating cash flow"],
        )
    ]

    grounded = build_grounded_answer(
        query="经营现金流为什么增长？",
        results=results,
    )

    assert grounded["conclusion"].startswith("结论：")
    assert "[PDF page 19]" in grounded["answer"]
    assert grounded["key_points"][0]["text"] == "cash generation improved"


def test_build_grounded_answer_uses_each_page_once() -> None:
    results = [
        make_result(
            page_number=19,
            text="Operating cash flow is an important performance measure.",
            matched_terms=["operating", "cash", "flow"],
            matched_concepts=["operating cash flow"],
            chunk_index=1,
        ),
        make_result(
            page_number=19,
            text="Cash generation supports the Group's operations.",
            matched_terms=["cash", "generated"],
            matched_concepts=["operating cash flow"],
            chunk_index=2,
        ),
    ]

    grounded = build_grounded_answer(
        query="operating cash flow",
        results=results,
    )

    assert len(grounded["evidence"]) == 1
    assert grounded["answer"].count("PDF page 19") == 1


def test_build_grounded_answer_removes_pdf_table_prefix() -> None:
    results = [
        make_result(
            page_number=29,
            text=(
                "(61) Property buybacks (144) (93) Restructuring (54) (55) "
                "We delivered Free cash flow of £1,957m, with cash generated "
                "from operations improving because of working capital."
            ),
            matched_terms=["cash", "generated", "working", "capital"],
            matched_concepts=["operating cash flow"],
        )
    ]

    grounded = build_grounded_answer(
        query="经营现金流为什么增长？",
        results=results,
    )

    assert grounded["evidence"][0]["excerpt"].startswith(
        "We delivered Free cash flow"
    )
    assert "(61)" not in grounded["evidence"][0]["excerpt"]


def test_build_grounded_answer_refuses_weak_word_overlap() -> None:
    results = [
        make_result(
            page_number=7,
            text="The football programme is mentioned in community news.",
            matched_terms=["football"],
            matched_concepts=[],
        )
    ]

    grounded = build_grounded_answer(
        query="公司为什么选择这个足球项目？",
        results=results,
    )

    assert grounded["is_supported"] is False
    assert grounded["evidence"] == []
    assert grounded["key_points"] == []
    assert grounded["answer"].startswith("证据不足")


def test_build_grounded_answer_rejects_missing_inputs() -> None:
    with pytest.raises(ValueError, match="question is required"):
        build_grounded_answer(query="", results=[])

    with pytest.raises(ValueError, match="evidence result is required"):
        build_grounded_answer(query="revenue", results=[])

    with pytest.raises(ValueError, match="max_evidence must be at least 1"):
        build_grounded_answer(
            query="revenue",
            results=[
                make_result(
                    page_number=1,
                    text="Revenue increased during the year.",
                    matched_terms=["revenue"],
                    matched_concepts=["revenue and sales"],
                )
            ],
            max_evidence=0,
        )
