"""Simple, traceable retrieval of evidence from annual-report pages."""

import re
from collections.abc import Iterable
from typing import TypedDict

from src.pdf_extractor import ExtractedPage
from src.semantic_retriever import semantic_similarity_scores


class ReportChunk(TypedDict):
    """A searchable text segment that keeps its original PDF page."""

    page_number: int
    chunk_index: int
    text: str


class SearchResult(TypedDict):
    """A ranked evidence segment and the terms that caused the match."""

    page_number: int
    chunk_index: int
    text: str
    score: float
    lexical_score: float
    semantic_score: float | None
    retrieval_method: str
    matched_terms: list[str]
    matched_concepts: list[str]


ENGLISH_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
WHITESPACE_PATTERN = re.compile(r"\s+")
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "by",
    "can",
    "company",
    "did",
    "do",
    "does",
    "for",
    "from",
    "how",
    "in",
    "it",
    "its",
    "is",
    "of",
    "on",
    "the",
    "to",
    "was",
    "were",
    "what",
    "why",
    "with",
    "year",
}

# The report is English, so common Chinese finance questions are mapped to
# the English vocabulary that is likely to appear in the source document.
CHINESE_FINANCE_TERMS = {
    "收入": {"revenue", "sales"},
    "营收": {"revenue", "sales"},
    "净利润率": {"net", "profit", "margin", "revenue"},
    "净利率": {"net", "profit", "margin", "revenue"},
    "净利润": {"net", "profit"},
    "利润": {"profit"},
    "盈利": {"profit"},
    "经营现金流": {"operating", "cash", "flow"},
    "投资现金流": {"investing", "cash", "flow"},
    "融资现金流": {"financing", "cash", "flow"},
    "现金流": {"cash", "flow"},
    "现金": {"cash"},
    "流动比率": {"current", "assets", "liabilities", "ratio"},
    "流动资产": {"current", "assets"},
    "总资产": {"total", "assets"},
    "资产": {"assets"},
    "流动负债": {"current", "liabilities"},
    "总负债": {"total", "liabilities"},
    "负债": {"liabilities"},
    "借款": {"borrowings"},
    "债务": {"debt", "borrowings"},
    "增长": {"growth", "increase"},
    "下降": {"decrease", "decline"},
    "风险": {"risk"},
}

# These concept groups allow differently worded questions to find the same
# financial evidence. They are deliberately small and auditable: the app can
# show which concept was recognised instead of hiding the ranking logic.
FINANCIAL_CONCEPTS = {
    "revenue and sales": {
        "triggers": (
            "revenue",
            "sales",
            "turnover",
            "top line",
            "收入",
            "营收",
        ),
        "terms": ("revenue", "sales", "growth"),
    },
    "profitability": {
        "triggers": (
            "profitability",
            "earnings",
            "bottom line",
            "net margin",
            "盈利能力",
            "利润率",
            "净利率",
            "净利润",
        ),
        "terms": ("profit", "earnings", "margin", "revenue"),
    },
    "operating cash flow": {
        "triggers": (
            "operating cash flow",
            "cash generation",
            "cash generated",
            "core operations",
            "day-to-day operations",
            "day to day operations",
            "经营现金流",
            "经营活动现金",
        ),
        "terms": (
            "operating",
            "cash",
            "flow",
            "generated",
            "working",
            "capital",
        ),
    },
    "liquidity": {
        "triggers": (
            "liquidity",
            "current ratio",
            "short-term obligations",
            "short term obligations",
            "cover its bills",
            "meet near-term payments",
            "流动比率",
            "流动性",
            "短期偿债",
        ),
        "terms": (
            "current",
            "assets",
            "liabilities",
            "working",
            "capital",
            "liquidity",
        ),
    },
    "leverage": {
        "triggers": (
            "leverage",
            "total liabilities",
            "capital structure",
            "debt burden",
            "asset base",
            "funded by obligations",
            "资产负债率",
            "负债资产比",
            "资本结构",
            "偿债压力",
        ),
        "terms": (
            "total",
            "assets",
            "liabilities",
            "borrowings",
            "debt",
        ),
    },
    "capital expenditure": {
        "triggers": (
            "capital expenditure",
            "capex",
            "investment in stores",
            "property plant and equipment",
            "资本开支",
            "扩张投资",
        ),
        "terms": (
            "capital",
            "expenditure",
            "purchase",
            "property",
            "plant",
            "equipment",
        ),
    },
}

# A report cover scored about 0.58 against "operating cash flow" in the local
# model. Requiring 0.60 prevents that weak thematic similarity from becoming
# evidence while retaining the 0.65 balance-sheet match for total liabilities.
SEMANTIC_RECALL_THRESHOLD = 0.60
LEXICAL_WEIGHT = 0.55
SEMANTIC_WEIGHT = 0.45


def _normalise_line(line: str) -> str:
    """Collapse unusual PDF whitespace while keeping the original wording."""
    return WHITESPACE_PATTERN.sub(
        " ",
        line.replace("\xa0", " "),
    ).strip()


def _normalise_search_token(token: str) -> str:
    """Treat simple forms such as 'increase' and 'increased' as one term."""
    if token.endswith("ed") and len(token) > 4:
        return token[:-1]
    return token


def chunk_report_pages(
    pages: Iterable[ExtractedPage],
    max_chars: int = 1_200,
    overlap_lines: int = 2,
) -> list[ReportChunk]:
    """Split each page into readable segments without losing page provenance."""
    if max_chars < 100:
        raise ValueError("max_chars must be at least 100.")
    if overlap_lines < 0:
        raise ValueError("overlap_lines cannot be negative.")

    chunks: list[ReportChunk] = []
    for page in pages:
        lines = [
            normalised
            for line in page["text"].splitlines()
            if (normalised := _normalise_line(line))
        ]
        start_line = 0
        chunk_index = 1

        while start_line < len(lines):
            selected_lines: list[str] = []
            current_length = 0
            cursor = start_line

            while cursor < len(lines):
                line = lines[cursor]
                extra_length = len(line) + (1 if selected_lines else 0)
                if selected_lines and current_length + extra_length > max_chars:
                    break

                selected_lines.append(line)
                current_length += extra_length
                cursor += 1

            chunks.append(
                {
                    "page_number": page["page_number"],
                    "chunk_index": chunk_index,
                    "text": "\n".join(selected_lines),
                }
            )
            chunk_index += 1

            if cursor >= len(lines):
                break

            # Repeating a small amount of text prevents a heading at the end
            # of one chunk from being separated from its figures in the next.
            next_start = max(cursor - overlap_lines, start_line + 1)
            start_line = next_start

    return chunks


def _query_features(query: str) -> tuple[dict[str, float], list[str]]:
    """Return weighted terms and any financial concepts found in the query."""
    normalised_query = _normalise_line(query).lower()
    term_weights = {
        _normalise_search_token(token): 2.0
        for token in ENGLISH_TOKEN_PATTERN.findall(normalised_query)
        if token not in STOP_WORDS and len(token) > 1
    }

    for chinese_phrase, english_terms in CHINESE_FINANCE_TERMS.items():
        if chinese_phrase in normalised_query:
            for term in english_terms:
                normalised_term = _normalise_search_token(term)
                term_weights[normalised_term] = max(
                    term_weights.get(normalised_term, 0),
                    1.5,
                )

    matched_concepts: list[str] = []
    for concept_name, concept_details in FINANCIAL_CONCEPTS.items():
        triggers = concept_details["triggers"]
        if not any(
            trigger in normalised_query
            for trigger in triggers
        ):
            continue

        matched_concepts.append(concept_name)
        for term in concept_details["terms"]:
            normalised_term = _normalise_search_token(term)
            term_weights[normalised_term] = max(
                term_weights.get(normalised_term, 0),
                1.0,
            )

    return term_weights, matched_concepts


def _score_chunk(
    chunk_text: str,
    query: str,
    query_term_weights: dict[str, float],
) -> tuple[float, list[str]]:
    """Calculate an explainable weighted score for one evidence segment."""
    normalised_text = _normalise_line(chunk_text).lower()
    text_tokens = [
        _normalise_search_token(token)
        for token in ENGLISH_TOKEN_PATTERN.findall(normalised_text)
    ]
    token_counts = {
        term: text_tokens.count(term)
        for term in query_term_weights
    }
    matched_terms = sorted(
        term
        for term, count in token_counts.items()
        if count > 0
    )
    if not matched_terms:
        return 0.0, []

    # Matching more of the question is more important than repeating one
    # common word many times. Repetition is capped to prevent long pages from
    # winning only because they contain many instances of "cash" or "assets".
    total_weight = sum(query_term_weights.values())
    matched_weight = sum(
        query_term_weights[term]
        for term in matched_terms
    )
    coverage = matched_weight / total_weight
    frequency = sum(
        min(token_counts[term], 3) * query_term_weights[term]
        for term in matched_terms
    )
    score = (coverage * 10) + frequency

    english_query = " ".join(
        ENGLISH_TOKEN_PATTERN.findall(query.lower())
    ).strip()
    if english_query and english_query in normalised_text:
        score += 5

    return score, matched_terms


def _financial_statement_bonus(query: str, chunk_text: str) -> float:
    """Prefer the full balance sheet over notes about one liability subtype."""
    normalised_query = _normalise_line(query).lower()
    normalised_text = _normalise_line(chunk_text).lower()
    asks_for_total_liabilities = "total liabilities" in normalised_query
    has_full_statement_scope = all(
        phrase in normalised_text
        for phrase in (
            "non-current liabilities",
            "net assets",
            "group balance sheet",
        )
    )
    return 0.25 if asks_for_total_liabilities and has_full_statement_scope else 0


def search_report_chunks(
    chunks: Iterable[ReportChunk],
    query: str,
    top_k: int = 3,
) -> list[SearchResult]:
    """Return the highest-scoring source segments for a user's question."""
    if top_k < 1:
        raise ValueError("top_k must be at least 1.")

    query_term_weights, matched_concepts = _query_features(query)
    if not query.strip():
        return []

    chunk_list = list(chunks)
    lexical_matches: list[tuple[float, list[str]]] = []
    for chunk in chunk_list:
        lexical_matches.append(
            _score_chunk(
                chunk_text=chunk["text"],
                query=query,
                query_term_weights=query_term_weights,
            )
            if query_term_weights
            else (0.0, [])
        )

    semantic_scores = semantic_similarity_scores(
        query=query,
        texts=[chunk["text"] for chunk in chunk_list],
    )
    maximum_lexical_score = max(
        (score for score, _ in lexical_matches),
        default=0,
    )

    results: list[SearchResult] = []
    for chunk, (lexical_score, matched_terms), semantic_score in zip(
        chunk_list,
        lexical_matches,
        (
            semantic_scores
            if semantic_scores is not None
            else [None] * len(chunk_list)
        ),
        strict=True,
    ):
        semantic_match = (
            semantic_score is not None
            and semantic_score >= SEMANTIC_RECALL_THRESHOLD
        )
        if lexical_score == 0 and not semantic_match:
            continue

        normalised_lexical_score = (
            lexical_score / maximum_lexical_score
            if maximum_lexical_score
            else 0
        )
        if semantic_score is None:
            score = normalised_lexical_score
            retrieval_method = "lexical"
        else:
            score = (
                LEXICAL_WEIGHT * normalised_lexical_score
                + SEMANTIC_WEIGHT * max(semantic_score, 0)
                + _financial_statement_bonus(query, chunk["text"])
            )
            retrieval_method = (
                "hybrid" if lexical_score > 0 else "semantic"
            )

        results.append(
            {
                "page_number": chunk["page_number"],
                "chunk_index": chunk["chunk_index"],
                "text": chunk["text"],
                "score": score,
                "lexical_score": lexical_score,
                "semantic_score": semantic_score,
                "retrieval_method": retrieval_method,
                "matched_terms": matched_terms,
                "matched_concepts": matched_concepts,
            }
        )

    results.sort(
        key=lambda result: (
            -result["score"],
            result["page_number"],
            result["chunk_index"],
        )
    )
    return results[:top_k]
