"""Choose an explainable investigation depth for each report question."""

import re
from typing import TypedDict


class RouteDecision(TypedDict):
    """The workflow and resource limits selected for one question."""

    mode: str
    label: str
    reason: str
    roles: list[str]
    matched_trigger: str | None
    tool_name: str | None
    top_k: int
    max_evidence: int
    max_challenges: int


WHITESPACE_PATTERN = re.compile(r"\s+")

# Deep-investigation triggers are checked first because a question about a
# management promise may also contain ordinary words such as "why" or "risk".
DEEP_INVESTIGATION_TRIGGERS = (
    "management promise",
    "management said",
    "guidance",
    "delivered on",
    "compare years",
    "across years",
    "contradiction",
    "contradict",
    "承诺",
    "兑现",
    "管理层",
    "指引",
    "跨年度",
    "多年",
    "矛盾",
    "去年说",
)
SKEPTICAL_INTENT_TRIGGERS = (
    "what drove",
    "driver",
    "why",
    "risk",
    "quality",
    "cover its",
    "为什么",
    "原因",
    "风险",
    "质量",
    "偿债",
    "驱动",
)
METRIC_TOOL_TRIGGERS = {
    "net_profit_margin": (
        "net profit margin",
        "net margin",
        "profit margin",
        "净利润率",
        "净利率",
    ),
    "revenue_growth": (
        "revenue growth",
        "sales growth",
        "收入增长率",
        "营收增长率",
    ),
    "current_ratio": (
        "current ratio",
        "流动比率",
    ),
    "liabilities_to_assets": (
        "liabilities-to-assets",
        "liabilities to assets",
        "debt ratio",
        "资产负债率",
        "负债资产比",
        "负债占资产",
    ),
    "total_liabilities": (
        "total liabilities",
        "总负债",
    ),
}
CHANGE_ANALYSIS_TRIGGERS = (
    "increase",
    "decrease",
    "增长",
    "下降",
    "变化",
)


def _normalise_query(query: str) -> str:
    """Make trigger matching stable across spacing and capitalisation."""
    return WHITESPACE_PATTERN.sub(" ", query).strip().lower()


def _first_trigger(
    query: str,
    triggers: tuple[str, ...],
) -> str | None:
    """Return the first visible routing trigger found in the question."""
    return next((trigger for trigger in triggers if trigger in query), None)


def route_question(query: str) -> RouteDecision:
    """Select quick, skeptical, or deep report investigation."""
    normalised_query = _normalise_query(query)
    if not normalised_query:
        raise ValueError("A question is required.")

    deep_trigger = _first_trigger(
        normalised_query,
        DEEP_INVESTIGATION_TRIGGERS,
    )
    if deep_trigger is not None:
        return {
            "mode": "deep_investigation",
            "label": "Deep investigation / 深度调查",
            "reason": (
                "The question involves management claims, cross-period "
                "comparison, or possible contradiction, so the router "
                "expands both evidence and challenge searches."
            ),
            "roles": [
                "Agent Router",
                "Analyst",
                "Skeptic",
                "Verifier",
            ],
            "matched_trigger": deep_trigger,
            "tool_name": None,
            "top_k": 10,
            "max_evidence": 5,
            "max_challenges": 3,
        }

    analysis_trigger = _first_trigger(
        normalised_query,
        SKEPTICAL_INTENT_TRIGGERS,
    )
    if analysis_trigger is not None:
        return {
            "mode": "skeptical_analysis",
            "label": "Skeptical analysis / 对抗式分析",
            "reason": (
                "The question asks about a driver, change, risk, or financial "
                "quality, so the router activates the Analyst, Skeptic, and "
                "Verifier sequence."
            ),
            "roles": ["Analyst", "Skeptic", "Verifier"],
            "matched_trigger": analysis_trigger,
            "tool_name": None,
            "top_k": 6,
            "max_evidence": 3,
            "max_challenges": 2,
        }

    for tool_name, triggers in METRIC_TOOL_TRIGGERS.items():
        tool_trigger = _first_trigger(normalised_query, triggers)
        if tool_trigger is None:
            continue
        return {
            "mode": "deterministic_metric",
            "label": "Python finance tool / Python财务工具",
            "reason": (
                "The question requests a supported financial metric, so the "
                "router calls a deterministic Python formula before running "
                "the cited evidence and safety checks."
            ),
            "roles": [
                "Python Finance Tool",
                "Evidence Retriever",
                "Skeptic safety scan",
                "Verifier",
            ],
            "matched_trigger": tool_trigger,
            "tool_name": tool_name,
            "top_k": 3,
            "max_evidence": 2,
            "max_challenges": 1,
        }

    change_trigger = _first_trigger(
        normalised_query,
        CHANGE_ANALYSIS_TRIGGERS,
    )
    if change_trigger is not None:
        return {
            "mode": "skeptical_analysis",
            "label": "Skeptical analysis / 对抗式分析",
            "reason": (
                "The question asks about a financial change, so the router "
                "expands retrieval and activates the Analyst, Skeptic, and "
                "Verifier sequence."
            ),
            "roles": ["Analyst", "Skeptic", "Verifier"],
            "matched_trigger": change_trigger,
            "tool_name": None,
            "top_k": 6,
            "max_evidence": 3,
            "max_challenges": 2,
        }

    return {
        "mode": "quick_evidence",
        "label": "Quick evidence review / 快速证据查找",
        "reason": (
            "The question appears to be a direct report lookup, so the "
            "router uses a smaller evidence set while retaining the safety "
            "scan and final verification."
        ),
        "roles": ["Evidence Retriever", "Skeptic safety scan", "Verifier"],
        "matched_trigger": None,
        "tool_name": None,
        "top_k": 3,
        "max_evidence": 2,
        "max_challenges": 1,
    }
