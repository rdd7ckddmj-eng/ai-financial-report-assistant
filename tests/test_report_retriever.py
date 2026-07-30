from pathlib import Path

import pytest

from src.pdf_extractor import extract_pdf_pages
from src.report_retriever import (
    chunk_report_pages,
    search_report_chunks,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = (
    PROJECT_ROOT / "data" / "reports" / "tesco_annual_report_2026.pdf"
)


def test_chunk_report_pages_preserves_page_numbers() -> None:
    pages = [
        {
            "page_number": 10,
            "text": (
                "Revenue\n"
                "Current year revenue increased.\n"
                "Profit for the year also increased."
            ),
        },
        {
            "page_number": 11,
            "text": "Operating cash flow\nCash generated from operations.",
        },
    ]

    chunks = chunk_report_pages(pages, max_chars=100)

    assert chunks
    assert {chunk["page_number"] for chunk in chunks} == {10, 11}
    assert all(chunk["text"].strip() for chunk in chunks)
    assert chunks[0]["chunk_index"] == 1


def test_search_report_chunks_ranks_the_relevant_evidence() -> None:
    chunks = chunk_report_pages(
        [
            {
                "page_number": 20,
                "text": "Revenue increased after higher sales volumes.",
            },
            {
                "page_number": 30,
                "text": (
                    "Operating cash flow increased because working capital "
                    "improved and cash generated from operations was higher."
                ),
            },
        ]
    )

    results = search_report_chunks(
        chunks,
        query="Why did operating cash flow increase?",
    )

    assert results
    assert results[0]["page_number"] == 30
    assert {"operating", "cash", "flow", "increase"}.issubset(
        results[0]["matched_terms"]
    )


def test_search_report_chunks_maps_chinese_finance_terms() -> None:
    chunks = chunk_report_pages(
        [
            {
                "page_number": 30,
                "text": (
                    "Operating cash flow increased because working capital "
                    "improved."
                ),
            },
            {
                "page_number": 40,
                "text": "Total liabilities include current liabilities.",
            },
        ]
    )

    results = search_report_chunks(chunks, query="经营现金流为什么增长？")

    assert results
    assert results[0]["page_number"] == 30
    assert "operating cash flow" in results[0]["matched_concepts"]


def test_chinese_question_finds_chinese_income_statement() -> None:
    chunks = chunk_report_pages(
        [
            {
                "page_number": 61,
                "text": (
                    "合并利润表\n"
                    "一、营业总收入 172,054,171,890.91\n"
                    "其中：营业收入 168,838,102,514.79"
                ),
            },
            {
                "page_number": 65,
                "text": (
                    "经营活动产生的现金流量净额 "
                    "61,522,204,989.08"
                ),
            },
        ]
    )

    results = search_report_chunks(chunks, query="营业收入是多少？")

    assert results
    assert results[0]["page_number"] == 61
    assert "营业收入" in results[0]["matched_terms"]
    assert results[0]["matched_concepts"] == ["revenue and sales"]


def test_chinese_question_finds_chinese_balance_sheet() -> None:
    chunks = chunk_report_pages(
        [
            {
                "page_number": 59,
                "text": (
                    "资产总计 303,834,844,020.66\n"
                    "非流动负债合计 265,113,293.91\n"
                    "负债合计 49,875,590,111.74\n"
                    "所有者权益合计 253,959,253,908.92"
                ),
            },
            {
                "page_number": 102,
                "text": "租赁负债合计 120,000,000.00",
            },
        ]
    )

    results = search_report_chunks(chunks, query="资产负债率是多少？")

    assert results
    assert results[0]["page_number"] == 59
    assert {"资产总计", "负债合计"}.issubset(
        results[0]["matched_terms"]
    )
    assert results[0]["matched_concepts"] == ["leverage"]


def test_chinese_question_finds_chinese_cash_flow_explanation() -> None:
    chunks = chunk_report_pages(
        [
            {
                "page_number": 20,
                "text": (
                    "经营活动产生的现金流量净额同比下降，"
                    "主要由于客户存款和同业存放款项净增加额减少。"
                ),
            },
            {
                "page_number": 61,
                "text": "营业收入 168,838,102,514.79",
            },
        ]
    )

    results = search_report_chunks(
        chunks,
        query="经营现金流为什么下降？",
    )

    assert results
    assert results[0]["page_number"] == 20
    assert "经营活动产生的现金流量净额" in results[0]["matched_terms"]
    assert results[0]["matched_concepts"] == ["operating cash flow"]


def test_search_report_chunks_maps_chinese_net_margin_short_name() -> None:
    chunks = chunk_report_pages(
        [
            {
                "page_number": 123,
                "text": "Revenue 73,712. Profit for the year 1,787.",
            },
            {
                "page_number": 128,
                "text": "Net cash generated from operating activities 3,906.",
            },
        ]
    )

    results = search_report_chunks(chunks, query="净利率是多少？")

    assert results
    assert results[0]["page_number"] == 123
    assert "profitability" in results[0]["matched_concepts"]


def test_search_report_chunks_maps_chinese_current_ratio() -> None:
    chunks = chunk_report_pages(
        [
            {
                "page_number": 125,
                "text": (
                    "Current assets were 8,483 and current liabilities "
                    "were 14,329."
                ),
            },
            {
                "page_number": 128,
                "text": "Operating cash flow was 3,906.",
            },
        ]
    )

    results = search_report_chunks(chunks, query="流动比率是多少？")

    assert results
    assert results[0]["page_number"] == 125
    assert results[0]["matched_concepts"] == ["liquidity"]


def test_search_report_chunks_maps_chinese_liabilities_ratio() -> None:
    chunks = chunk_report_pages(
        [
            {
                "page_number": 125,
                "text": "Total assets were 39,474 and liabilities 28,017.",
            },
            {
                "page_number": 128,
                "text": "Operating cash flow was 3,906.",
            },
        ]
    )

    results = search_report_chunks(chunks, query="资产负债率是多少？")

    assert results
    assert results[0]["page_number"] == 125
    assert results[0]["matched_concepts"] == ["leverage"]


def test_concept_search_understands_different_liquidity_wording() -> None:
    chunks = chunk_report_pages(
        [
            {
                "page_number": 50,
                "text": (
                    "Current assets were 800 and current liabilities were "
                    "1,000, resulting in negative working capital."
                ),
            },
            {
                "page_number": 60,
                "text": "Revenue increased because sales volumes were higher.",
            },
        ]
    )

    results = search_report_chunks(
        chunks,
        query="Can the company cover its short-term obligations?",
    )

    assert results
    assert results[0]["page_number"] == 50
    assert results[0]["matched_concepts"] == ["liquidity"]


def test_concept_search_understands_top_line_wording() -> None:
    chunks = chunk_report_pages(
        [
            {
                "page_number": 20,
                "text": "Revenue and sales growth were supported by volume.",
            },
            {
                "page_number": 30,
                "text": "Total liabilities and borrowings declined.",
            },
        ]
    )

    results = search_report_chunks(
        chunks,
        query="What drove top line performance?",
    )

    assert results
    assert results[0]["page_number"] == 20
    assert "revenue and sales" in results[0]["matched_concepts"]


def test_lexical_search_understands_total_liabilities_scope() -> None:
    chunks = chunk_report_pages(
        [
            {
                "page_number": 125,
                "text": (
                    "Non-current liabilities were 13,688. Net assets were "
                    "11,457. Group balance sheet. Current liabilities were "
                    "14,329."
                ),
            },
            {
                "page_number": 147,
                "text": "Total lease liabilities were 7,884.",
            },
            {
                "page_number": 161,
                "text": "Total insurance contract liabilities were 772.",
            },
        ]
    )

    results = search_report_chunks(
        chunks,
        query="What are total liabilities?",
    )

    assert results[0]["page_number"] == 125
    assert results[0]["matched_concepts"] == ["leverage"]
    assert results[0]["retrieval_method"] == "lexical"
    assert results[0]["semantic_score"] is None


def test_search_report_chunks_returns_nothing_for_empty_or_unmatched_query() -> None:
    chunks = chunk_report_pages(
        [{"page_number": 1, "text": "Annual report cover"}]
    )

    assert search_report_chunks(chunks, query="") == []
    assert search_report_chunks(chunks, query="operating cash flow") == []


def test_search_report_chunks_rejects_invalid_top_k() -> None:
    with pytest.raises(ValueError, match="top_k must be at least 1"):
        search_report_chunks([], query="revenue", top_k=0)


def test_real_report_search_finds_the_cash_flow_statement() -> None:
    if not REPORT_PATH.exists():
        pytest.skip("The public Tesco PDF is stored locally and not committed.")

    pages = extract_pdf_pages(REPORT_PATH.read_bytes())
    chunks = chunk_report_pages(pages)
    results = search_report_chunks(
        chunks,
        query=(
            "Group cash flow statement operating investing financing "
            "net increase cash equivalents"
        ),
        top_k=5,
    )

    assert any(result["page_number"] == 128 for result in results)


def test_real_report_concept_search_finds_balance_sheet_liquidity() -> None:
    if not REPORT_PATH.exists():
        pytest.skip("The public Tesco PDF is stored locally and not committed.")

    pages = extract_pdf_pages(REPORT_PATH.read_bytes())
    chunks = chunk_report_pages(pages)
    results = search_report_chunks(
        chunks,
        query="Can the company cover its short-term obligations?",
        top_k=5,
    )

    assert any(result["page_number"] == 125 for result in results)


def test_real_report_search_finds_total_liabilities_statement() -> None:
    if not REPORT_PATH.exists():
        pytest.skip("The public Tesco PDF is stored locally and not committed.")

    pages = extract_pdf_pages(REPORT_PATH.read_bytes())
    chunks = chunk_report_pages(pages)
    results = search_report_chunks(
        chunks,
        query="What are total liabilities?",
        top_k=3,
    )

    assert any(result["page_number"] == 125 for result in results)
    assert results[0]["matched_concepts"] == ["leverage"]
