import pytest

from src.agent_router import route_question


def test_router_uses_quick_review_for_direct_lookup() -> None:
    decision = route_question("What was revenue?")

    assert decision["mode"] == "quick_evidence"
    assert decision["top_k"] == 3
    assert decision["max_evidence"] == 2
    assert decision["max_challenges"] == 1


def test_router_uses_skeptical_analysis_for_driver_question() -> None:
    decision = route_question("经营现金流为什么增长？")

    assert decision["mode"] == "skeptical_analysis"
    assert decision["matched_trigger"] == "why" or (
        decision["matched_trigger"] == "为什么"
    )
    assert decision["roles"] == ["Analyst", "Skeptic", "Verifier"]
    assert decision["top_k"] == 6


@pytest.mark.parametrize(
    ("question", "tool_name"),
    [
        ("净利率是多少？", "net_profit_margin"),
        ("What is revenue growth?", "revenue_growth"),
        ("流动比率是多少？", "current_ratio"),
        ("What is the liabilities-to-assets ratio?", "liabilities_to_assets"),
        ("What are total liabilities?", "total_liabilities"),
    ],
)
def test_router_selects_supported_python_metric_tool(
    question: str,
    tool_name: str,
) -> None:
    decision = route_question(question)

    assert decision["mode"] == "deterministic_metric"
    assert decision["tool_name"] == tool_name
    assert decision["roles"][0] == "Python Finance Tool"


def test_why_question_uses_analysis_instead_of_metric_tool() -> None:
    decision = route_question("Why did revenue growth change?")

    assert decision["mode"] == "skeptical_analysis"
    assert decision["tool_name"] is None


def test_router_uses_deep_investigation_for_management_promise() -> None:
    decision = route_question("管理层去年的承诺是否兑现？")

    assert decision["mode"] == "deep_investigation"
    assert decision["matched_trigger"] in {"承诺", "兑现", "管理层"}
    assert decision["top_k"] == 10
    assert decision["max_evidence"] == 5
    assert decision["max_challenges"] == 3


def test_deep_route_takes_priority_over_general_risk_trigger() -> None:
    decision = route_question(
        "What risk could prevent management from delivering on its guidance?"
    )

    assert decision["mode"] == "deep_investigation"
    assert decision["matched_trigger"] == "guidance"


def test_router_rejects_empty_question() -> None:
    with pytest.raises(ValueError, match="question is required"):
        route_question("   ")
