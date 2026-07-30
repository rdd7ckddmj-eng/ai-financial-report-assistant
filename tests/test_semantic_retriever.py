from src.semantic_retriever import (
    MAX_SEMANTIC_PASSAGES,
    semantic_similarity_scores,
)


def test_chinese_query_uses_lightweight_lexical_fallback() -> None:
    result = semantic_similarity_scores(
        "营业收入是多少？",
        ["合并利润表中的营业收入"],
    )

    assert result is None


def test_large_report_uses_lightweight_lexical_fallback() -> None:
    texts = ["Annual report passage"] * (MAX_SEMANTIC_PASSAGES + 1)

    result = semantic_similarity_scores("revenue", texts)

    assert result is None
