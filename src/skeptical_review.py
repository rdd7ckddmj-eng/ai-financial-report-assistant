"""Find cited offsets and limitations that may weaken a report answer."""

import re
from typing import TypedDict

from src.grounded_answer import GroundedAnswer
from src.report_retriever import SearchResult


class ChallengeEvidence(TypedDict):
    """One exact report passage that qualifies or challenges an answer."""

    page_number: int
    excerpt: str
    trigger: str


class SkepticalReview(TypedDict):
    """A rule-based challenge review with traceable source passages."""

    status: str
    summary: str
    challenges: list[ChallengeEvidence]
    limitation: str


WHITESPACE_PATTERN = re.compile(r"\s+")
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")
CHINESE_CHARACTER_PATTERN = re.compile(r"[\u4e00-\u9fff]")

# Explicit qualification words are stronger than generic risk words. Keeping
# this list visible makes the first Skeptic Mode easy to audit and improve.
CHALLENGE_MARKERS = {
    "partly offset by": 5,
    "offset by": 5,
    "however": 4,
    "although": 4,
    "despite": 4,
    "could adversely": 4,
    "headwind": 3,
    "uncertain": 2,
}


def _normalise_text(text: str) -> str:
    """Turn PDF line breaks and control characters into readable prose."""
    cleaned = text.replace("\xa0", " ").replace("\x07", " ")
    return WHITESPACE_PATTERN.sub(" ", cleaned).strip()


def _truncate_excerpt(text: str, max_chars: int = 320) -> str:
    """Keep the original source wording while limiting display length."""
    if len(text) <= max_chars:
        return text

    shortened = text[: max_chars + 1]
    last_space = shortened.rfind(" ")
    if last_space > max_chars * 0.7:
        shortened = shortened[:last_space]
    else:
        shortened = shortened[:max_chars]
    return f"{shortened.rstrip()}…"


def _challenge_trigger(sentence: str) -> tuple[str, int] | None:
    """Return the strongest challenge marker contained in a sentence."""
    lower_sentence = sentence.lower()
    matches = [
        (marker, weight)
        for marker, weight in CHALLENGE_MARKERS.items()
        if re.search(rf"\b{re.escape(marker)}\b", lower_sentence)
    ]
    return max(matches, key=lambda item: item[1]) if matches else None


def _challenge_candidates(
    results: list[SearchResult],
) -> list[tuple[int, str, str, int, int]]:
    """Collect page, text, marker, weight, and relevance for each challenge."""
    candidates: list[tuple[int, str, str, int, int]] = []
    seen_passages: set[tuple[int, str]] = set()

    for result in results:
        normalised_text = _normalise_text(result["text"])
        sentences = [
            sentence.strip()
            for sentence in SENTENCE_SPLIT_PATTERN.split(normalised_text)
            if len(sentence.strip()) >= 40
        ]
        for sentence in sentences:
            trigger = _challenge_trigger(sentence)
            if trigger is None:
                continue

            excerpt = _truncate_excerpt(sentence)
            passage_key = (result["page_number"], excerpt)
            if passage_key in seen_passages:
                continue

            marker, marker_weight = trigger
            lower_sentence = sentence.lower()
            matched_term_count = sum(
                term in lower_sentence
                for term in result["matched_terms"]
            )
            # A generic word such as "risk" is not a valid challenge unless
            # the same sentence is also connected to the user's finance topic.
            if matched_term_count == 0:
                continue
            candidates.append(
                (
                    result["page_number"],
                    excerpt,
                    marker,
                    marker_weight,
                    matched_term_count,
                )
            )
            seen_passages.add(passage_key)

    candidates.sort(
        key=lambda item: (
            -item[3],
            -item[4],
            item[0],
        )
    )
    return candidates


def build_skeptical_review(
    query: str,
    answer: GroundedAnswer,
    results: list[SearchResult],
    max_challenges: int = 2,
) -> SkepticalReview:
    """Challenge a supported answer using only cited retrieved report text."""
    if not query.strip():
        raise ValueError("A question is required.")
    if max_challenges < 1:
        raise ValueError("max_challenges must be at least 1.")

    chinese_query = bool(CHINESE_CHARACTER_PATTERN.search(query))
    limitation = (
        "This first Skeptic Mode scans retrieved text for explicit offsets "
        "and limitations. It may miss indirectly worded counter-evidence."
    )

    if not answer["is_supported"]:
        summary = (
            "原始结论的证据不足，因此质疑模式没有继续审查。"
            if chinese_query
            else (
                "The original conclusion lacked sufficient evidence, so "
                "Skeptic Mode did not continue the review."
            )
        )
        return {
            "status": "not_applicable",
            "summary": summary,
            "challenges": [],
            "limitation": limitation,
        }

    candidates = _challenge_candidates(results)
    challenges = [
        {
            "page_number": page_number,
            "excerpt": excerpt,
            "trigger": trigger,
        }
        for page_number, excerpt, trigger, _, _ in candidates[:max_challenges]
    ]

    if challenges:
        summary = (
            "质疑结果：年报中存在需要与主要结论同时披露的抵消因素或限制。"
            if chinese_query
            else (
                "Skeptic result: the report contains offsets or limitations "
                "that should be disclosed with the main conclusion."
            )
        )
        status = "counter_evidence_found"
    else:
        summary = (
            "质疑结果：当前检索范围内没有发现明确的反方证据，"
            "但这不代表不存在其他风险。"
            if chinese_query
            else (
                "Skeptic result: no explicit counter-evidence was found in "
                "the retrieved passages, but other risks may still exist."
            )
        )
        status = "no_counter_evidence_found"

    return {
        "status": status,
        "summary": summary,
        "challenges": challenges,
        "limitation": limitation,
    }
