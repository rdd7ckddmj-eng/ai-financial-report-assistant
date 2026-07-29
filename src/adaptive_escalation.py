"""Escalate report analysis when deterministic risk signals appear."""

import re
from typing import TypedDict

from src.agent_router import RouteDecision
from src.answer_verifier import VerificationResult
from src.grounded_answer import GroundedAnswer
from src.report_retriever import SearchResult
from src.skeptical_review import SkepticalReview


class EscalationDecision(TypedDict):
    """One transparent decision to retain or increase analysis depth."""

    escalated: bool
    summary: str
    signals: list[str]
    route: RouteDecision


PERIOD_53_PATTERN = re.compile(r"\b53[\s-]*weeks?\b", re.IGNORECASE)
PERIOD_52_PATTERN = re.compile(r"\b52[\s-]*weeks?\b", re.IGNORECASE)
MATERIAL_CHALLENGE_TRIGGERS = {
    "partly offset by",
    "offset by",
    "however",
    "although",
    "despite",
    "could adversely",
}


def _contains_period_mismatch(results: list[SearchResult]) -> bool:
    """Detect the common 53-week versus 52-week comparability problem."""
    combined_text = " ".join(result["text"] for result in results)
    return bool(
        PERIOD_53_PATTERN.search(combined_text)
        and PERIOD_52_PATTERN.search(combined_text)
    )


def _collect_signals(
    answer: GroundedAnswer | None,
    skeptical_review: SkepticalReview | None,
    verification: VerificationResult | None,
    results: list[SearchResult],
    metric_available: bool | None,
    check_period_comparability: bool,
) -> list[str]:
    """Return visible reasons that justify spending more analysis effort."""
    signals: list[str] = []

    if not results:
        signals.append(
            "No matching report evidence was found / 未找到匹配的报告证据"
        )
    elif answer is not None and not answer["is_supported"]:
        signals.append(
            "Retrieved evidence was too weak / 当前检索证据强度不足"
        )

    if metric_available is False:
        signals.append(
            "The Python metric lacked required statement data / "
            "Python 指标缺少必要报表数据"
        )

    if (
        skeptical_review is not None
        and skeptical_review["status"] == "counter_evidence_found"
        and any(
            challenge["trigger"] in MATERIAL_CHALLENGE_TRIGGERS
            for challenge in skeptical_review["challenges"]
        )
    ):
        signals.append(
            "Counter-evidence or an offset was found / "
            "发现反方证据或抵消因素"
        )

    if check_period_comparability and _contains_period_mismatch(results):
        signals.append(
            "The evidence compares 53 weeks with 52 weeks / "
            "证据涉及 53 周与 52 周的不可直接比较"
        )

    if verification is not None and verification["status"] == "rejected":
        signals.append(
            "The deterministic verifier rejected the draft / "
            "确定性审计器拒绝了初稿"
        )

    return signals


def _escalated_route(current_route: RouteDecision) -> RouteDecision:
    """Increase analysis by exactly one bounded workflow level."""
    if current_route["mode"] in {
        "quick_evidence",
        "deterministic_metric",
    }:
        roles = ["Analyst", "Skeptic", "Verifier"]
        if current_route["tool_name"] is not None:
            roles.insert(0, "Python Finance Tool")
        return {
            "mode": "skeptical_analysis",
            "label": "Adaptive skeptical analysis / 自适应对抗分析",
            "reason": (
                "Deterministic post-retrieval signals require a broader "
                "evidence set and a stronger challenge review."
            ),
            "roles": roles,
            "matched_trigger": "adaptive evidence signal",
            "tool_name": current_route["tool_name"],
            "top_k": 6,
            "max_evidence": 3,
            "max_challenges": 2,
        }

    return {
        "mode": "deep_investigation",
        "label": "Adaptive deep investigation / 自适应深度调查",
        "reason": (
            "The analytical review found a material evidence or audit "
            "signal, so the router expands to its maximum bounded depth."
        ),
        "roles": ["Agent Router", "Analyst", "Skeptic", "Verifier"],
        "matched_trigger": "adaptive evidence signal",
        "tool_name": current_route["tool_name"],
        "top_k": 10,
        "max_evidence": 5,
        "max_challenges": 3,
    }


def decide_adaptive_escalation(
    current_route: RouteDecision,
    answer: GroundedAnswer | None,
    skeptical_review: SkepticalReview | None,
    verification: VerificationResult | None,
    results: list[SearchResult],
    metric_available: bool | None = None,
) -> EscalationDecision:
    """Keep the initial route or increase it once for visible safety reasons."""
    signals = _collect_signals(
        answer=answer,
        skeptical_review=skeptical_review,
        verification=verification,
        results=results,
        metric_available=metric_available,
        check_period_comparability=(
            current_route["tool_name"] == "revenue_growth"
            or current_route["mode"] in {
                "skeptical_analysis",
                "deep_investigation",
            }
        ),
    )

    if not signals:
        return {
            "escalated": False,
            "summary": (
                "No escalation: the initial evidence and audit checks did "
                "not produce a material risk signal."
            ),
            "signals": [],
            "route": current_route,
        }

    if current_route["mode"] == "deep_investigation":
        return {
            "escalated": False,
            "summary": (
                "The route is already at the maximum bounded investigation "
                "depth; the detected signals remain visible."
            ),
            "signals": signals,
            "route": current_route,
        }

    return {
        "escalated": True,
        "summary": (
            "Escalated automatically: one or more deterministic safety "
            "signals require a broader review."
        ),
        "signals": signals,
        "route": _escalated_route(current_route),
    }
