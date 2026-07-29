"""Build short answers using only retrieved annual-report evidence."""

import re
from typing import TypedDict

from src.report_retriever import SearchResult


class AnswerEvidence(TypedDict):
    """One extract used in an answer and its source PDF page."""

    page_number: int
    excerpt: str


class AnswerPoint(TypedDict):
    """One evidence-backed point shown in the structured answer."""

    page_number: int
    text: str


class GroundedAnswer(TypedDict):
    """An extractive answer whose claims can be traced to report pages."""

    is_supported: bool
    conclusion: str
    answer: str
    key_points: list[AnswerPoint]
    evidence: list[AnswerEvidence]
    concepts: list[str]
    limitation: str


WHITESPACE_PATTERN = re.compile(r"\s+")
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")
CHINESE_CHARACTER_PATTERN = re.compile(r"[\u4e00-\u9fff]")
PROSE_START_PATTERN = re.compile(
    r"\b(?:We|The Group|The company|The policy|This|Cash|Operating|"
    r"Revenue|Profit|Current|Total|Liquidity|Strong)\b"
)
CAUSAL_QUERY_PATTERN = re.compile(
    r"\b(?:why|driver|drivers|driven|cause|causes)\b|为什么|原因|推动|驱动",
    re.IGNORECASE,
)
CAUSE_MARKERS = (
    "driven by",
    "because of",
    "because",
    "due to",
    "supported by",
    "reflecting",
)
CHINESE_CONCEPT_LABELS = {
    "revenue and sales": "收入与销售",
    "profitability": "盈利能力",
    "operating cash flow": "经营现金流",
    "liquidity": "流动性",
    "leverage": "杠杆与资本结构",
    "capital expenditure": "资本开支",
}


def _normalise_text(text: str) -> str:
    """Collapse PDF line breaks and unusual spaces into readable prose."""
    return WHITESPACE_PATTERN.sub(
        " ",
        text.replace("\xa0", " "),
    ).strip()


def _remove_table_prefix(text: str) -> str:
    """Start at the first clear prose sentence after PDF table fragments."""
    match = PROSE_START_PATTERN.search(text)
    if match is None or match.start() == 0:
        return text

    prefix = text[: match.start()]
    looks_like_table_fragment = (
        len(prefix) >= 20
        and (
            any(character.isdigit() for character in prefix)
            or "(" in prefix
            or "–" in prefix
        )
    )
    return text[match.start() :] if looks_like_table_fragment else text


def _candidate_passages(text: str) -> list[str]:
    """Return sentence and line candidates without inventing new wording."""
    normalised_text = _normalise_text(text)
    sentences = [
        sentence.strip()
        for sentence in SENTENCE_SPLIT_PATTERN.split(normalised_text)
        if len(sentence.strip()) >= 35
    ]
    lines = [
        _normalise_text(line)
        for line in text.splitlines()
        if len(_normalise_text(line)) >= 35
    ]

    candidates: list[str] = []
    for candidate in [*sentences, *lines]:
        candidate = _remove_table_prefix(candidate)
        if candidate not in candidates:
            candidates.append(candidate)

    return candidates or [normalised_text]


def _truncate_excerpt(text: str, max_chars: int = 280) -> str:
    """Keep evidence readable while preserving its original wording."""
    if len(text) <= max_chars:
        return text

    shortened = text[: max_chars + 1]
    last_space = shortened.rfind(" ")
    if last_space > max_chars * 0.7:
        shortened = shortened[:last_space]
    else:
        shortened = shortened[:max_chars]
    return f"{shortened.rstrip()}…"


def _select_excerpt(result: SearchResult) -> str:
    """Choose the passage containing the most of the matched search terms."""
    candidates = _candidate_passages(result["text"])

    def candidate_score(candidate: str) -> tuple[int, float]:
        lower_candidate = candidate.lower()
        matched_count = sum(
            term in lower_candidate
            for term in result["matched_terms"]
        )
        # A moderate amount of context is preferable when term coverage ties.
        readable_length = min(len(candidate), 220) / 220
        return matched_count, readable_length

    best_candidate = max(candidates, key=candidate_score)
    return _truncate_excerpt(best_candidate)


def _unique_concepts(results: list[SearchResult]) -> list[str]:
    """Preserve the retrieval order while removing duplicate concepts."""
    concepts: list[str] = []
    for result in results:
        for concept in result.get("matched_concepts", []):
            if concept not in concepts:
                concepts.append(concept)
    return concepts


def _has_sufficient_evidence(results: list[SearchResult]) -> bool:
    """Require multiple lexical matches or a strong local semantic match."""
    if not results:
        return False

    strongest_result = results[0]
    matched_terms = set(strongest_result["matched_terms"])
    recognised_concept = bool(strongest_result.get("matched_concepts"))
    strong_semantic_match = (
        strongest_result.get("semantic_score") is not None
        and strongest_result["semantic_score"] >= 0.60
    )
    return len(matched_terms) >= 2 or (
        recognised_concept and len(matched_terms) >= 1
    ) or strong_semantic_match


def _concept_text(query: str, concepts: list[str]) -> str:
    """Use readable Chinese concept names for Chinese questions."""
    if not concepts:
        return "相关财务主题" if CHINESE_CHARACTER_PATTERN.search(query) else (
            "the requested topic"
        )
    if CHINESE_CHARACTER_PATTERN.search(query):
        return "、".join(
            CHINESE_CONCEPT_LABELS.get(concept, concept)
            for concept in concepts
        )
    return ", ".join(concepts)


def _extract_driver(excerpt: str) -> str | None:
    """Return the exact causal phrase after markers such as 'driven by'."""
    lower_excerpt = excerpt.lower()
    marker_positions = [
        (lower_excerpt.find(marker), marker)
        for marker in CAUSE_MARKERS
        if lower_excerpt.find(marker) >= 0
    ]
    if not marker_positions:
        return None

    marker_position, marker = min(marker_positions)
    driver = excerpt[marker_position + len(marker) :].strip(" :;,.")
    return _truncate_excerpt(driver, max_chars=180) if driver else None


def _build_key_points(
    query: str,
    evidence: list[AnswerEvidence],
) -> tuple[list[AnswerPoint], bool]:
    """Prefer exact causal phrases for why-questions; otherwise use extracts."""
    causal_query = bool(CAUSAL_QUERY_PATTERN.search(query))
    key_points: list[AnswerPoint] = []
    used_driver_extraction = False
    used_text: set[str] = set()

    for item in evidence:
        driver = _extract_driver(item["excerpt"]) if causal_query else None
        point_text = driver or item["excerpt"]
        used_driver_extraction = used_driver_extraction or driver is not None
        if point_text in used_text:
            continue
        key_points.append(
            {
                "page_number": item["page_number"],
                "text": point_text,
            }
        )
        used_text.add(point_text)

    return key_points, used_driver_extraction


def build_grounded_answer(
    query: str,
    results: list[SearchResult],
    max_evidence: int = 3,
) -> GroundedAnswer:
    """Create a concise answer made only from cited source extracts."""
    if not query.strip():
        raise ValueError("A question is required.")
    if not results:
        raise ValueError("At least one evidence result is required.")
    if max_evidence < 1:
        raise ValueError("max_evidence must be at least 1.")

    concepts = _unique_concepts(results)
    concept_text = _concept_text(query, concepts)
    chinese_query = bool(CHINESE_CHARACTER_PATTERN.search(query))
    if not _has_sufficient_evidence(results):
        conclusion = (
            "证据不足：检索结果与问题只存在较弱的词语重合，"
            "因此没有生成报告结论。"
            if chinese_query
            else (
                "Insufficient evidence: the retrieved text only has a weak "
                "word overlap with the question, so no report conclusion "
                "was generated."
            )
        )
        return {
            "is_supported": False,
            "conclusion": conclusion,
            "answer": conclusion,
            "key_points": [],
            "evidence": [],
            "concepts": concepts,
            "limitation": (
                "Try a more specific financial question. No low-confidence "
                "passage was presented as an answer."
            ),
        }

    evidence: list[AnswerEvidence] = []
    used_pages: set[int] = set()
    for result in results:
        page_number = result["page_number"]
        if page_number in used_pages:
            continue

        evidence.append(
            {
                "page_number": page_number,
                "excerpt": _select_excerpt(result),
            }
        )
        used_pages.add(page_number)
        if len(evidence) == max_evidence:
            break

    key_points, used_driver_extraction = _build_key_points(query, evidence)
    if chinese_query:
        conclusion = (
            f"结论：年报将{concept_text}的变化归因于以下因素。"
            if used_driver_extraction
            else f"结论：年报中找到了与{concept_text}直接相关的证据。"
        )
        cited_points = "；".join(
            f"{number}. {point['text']} "
            f"[PDF page {point['page_number']}]"
            for number, point in enumerate(key_points, start=1)
        )
        answer = f"{conclusion} 依据：{cited_points}。"
    else:
        conclusion = (
            f"Conclusion: the annual report attributes the change in "
            f"{concept_text} to the factors below."
            if used_driver_extraction
            else (
                "Conclusion: the annual report contains direct evidence "
                f"about {concept_text}."
            )
        )
        cited_points = " ".join(
            f"{number}. {point['text']} "
            f"[PDF page {point['page_number']}]"
            for number, point in enumerate(key_points, start=1)
        )
        answer = f"{conclusion} Evidence: {cited_points}"

    return {
        "is_supported": True,
        "conclusion": conclusion,
        "answer": answer,
        "key_points": key_points,
        "evidence": evidence,
        "concepts": concepts,
        "limitation": (
            "This is an extractive answer assembled from cited report text. "
            "It does not infer facts beyond the evidence and is not "
            "investment advice."
        ),
    }
