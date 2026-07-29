from src.adaptive_escalation import decide_adaptive_escalation
from src.agent_coordinator import (
    build_agent_audit_record,
    run_agent_workflow,
)
from src.agent_router import route_question


def _chunks() -> list[dict]:
    return [
        {
            "page_number": 29,
            "chunk_index": 1,
            "text": (
                "Operating cash flow increased because working capital "
                "improved. The increase was partly offset by higher tax."
            ),
        },
        {
            "page_number": 123,
            "chunk_index": 1,
            "text": "Revenue 73,712. Profit for the year 1,787.",
        },
    ]


def _income_figures() -> dict:
    return {
        "current_revenue": 73_712.0,
        "previous_revenue": 69_916.0,
        "current_net_profit": 1_787.0,
        "previous_net_profit": 1_630.0,
        "unit": "£m",
        "page_number": 123,
        "current_period_weeks": 53,
        "previous_period_weeks": 52,
    }


def test_coordinator_runs_agents_in_explicit_handoff_order() -> None:
    run = run_agent_workflow(
        query="Why did operating cash flow increase?",
        chunks=_chunks(),
        route=route_question("Why did operating cash flow increase?"),
    )

    assert [step["role"] for step in run["trace"]] == [
        "Agent Router",
        "Evidence Retriever",
        "Analyst",
        "Skeptic",
        "Verifier",
        "Agent Coordinator",
    ]
    assert run["answer"] is not None
    assert run["skeptical_review"]["status"] == "counter_evidence_found"
    assert run["verification"]["status"] == "approved_with_caveats"
    assert 29 in run["trace"][-1]["source_pages"]


def test_coordinator_stops_downstream_agents_without_evidence() -> None:
    run = run_agent_workflow(
        query="football sponsorship details",
        chunks=_chunks(),
        route=route_question("football sponsorship details"),
    )

    assert run["results"] == []
    assert run["answer"] is None
    assert run["verification"] is None
    assert [step["role"] for step in run["trace"]] == [
        "Agent Router",
        "Evidence Retriever",
        "Agent Coordinator",
    ]
    assert run["trace"][-1]["status"] == "stopped"


def test_coordinator_records_python_metric_with_source_page() -> None:
    run = run_agent_workflow(
        query="净利率是多少？",
        chunks=_chunks(),
        route=route_question("净利率是多少？"),
        income_figures=_income_figures(),
    )

    assert run["metric_result"]["display_value"] == "2.4%"
    tool_step = run["trace"][1]
    assert tool_step["role"] == "Python Finance Tool"
    assert tool_step["status"] == "completed"
    assert tool_step["source_pages"] == [123]


def test_escalated_run_reuses_the_existing_metric_result() -> None:
    query = "What is revenue growth?"
    initial_run = run_agent_workflow(
        query=query,
        chunks=_chunks(),
        route=route_question(query),
        income_figures=_income_figures(),
    )

    escalated_run = run_agent_workflow(
        query=query,
        chunks=_chunks(),
        route={
            **initial_run["route"],
            "mode": "skeptical_analysis",
            "top_k": 6,
            "max_evidence": 3,
            "max_challenges": 2,
        },
        income_figures=_income_figures(),
        existing_metric_result=initial_run["metric_result"],
    )

    assert escalated_run["metric_result"] is initial_run["metric_result"]
    assert escalated_run["trace"][1]["status"] == "reused"


def test_audit_record_keeps_routes_handoffs_and_cited_pages() -> None:
    query = "Why did operating cash flow increase?"
    route = route_question(query)
    initial_run = run_agent_workflow(
        query=query,
        chunks=_chunks(),
        route=route,
    )
    escalation = decide_adaptive_escalation(
        current_route=route,
        answer=initial_run["answer"],
        skeptical_review=initial_run["skeptical_review"],
        verification=initial_run["verification"],
        results=initial_run["results"],
    )
    final_run = run_agent_workflow(
        query=query,
        chunks=_chunks(),
        route=escalation["route"],
    )

    audit = build_agent_audit_record(
        report_name="sample.pdf",
        initial_route=route,
        escalation=escalation,
        initial_run=initial_run,
        final_run=final_run,
    )

    assert audit["schema_version"] == "1.0"
    assert audit["report_name"] == "sample.pdf"
    assert audit["adaptive_escalation"]["escalated"] is True
    assert audit["verification"]["status"] == "approved_with_caveats"
    assert audit["cited_pdf_pages"] == [29]
