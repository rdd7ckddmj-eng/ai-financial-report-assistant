from src.semantic_retriever import (
    ENABLE_LOCAL_EMBEDDINGS,
    MAX_SEMANTIC_PASSAGES,
    semantic_similarity_scores,
)


def test_local_embeddings_are_disabled_by_default() -> None:
    assert ENABLE_LOCAL_EMBEDDINGS is False
    assert semantic_similarity_scores(
        "revenue",
        ["Revenue increased during the year."],
    ) is None


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
