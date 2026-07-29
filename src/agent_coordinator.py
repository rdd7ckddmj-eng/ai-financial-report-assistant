"""Coordinate deterministic report agents through one shared run state."""

from typing import TypedDict

from src.adaptive_escalation import EscalationDecision
from src.agent_router import RouteDecision
from src.answer_verifier import VerificationResult, verify_answer
from src.balance_sheet_extractor import BalanceSheetFigures
from src.financial_statement_extractor import IncomeStatementFigures
from src.grounded_answer import GroundedAnswer, build_grounded_answer
from src.report_metric_tool import (
    MetricToolResult,
    run_report_metric_tool,
)
from src.report_retriever import (
    ReportChunk,
    SearchResult,
    search_report_chunks,
)
from src.skeptical_review import (
    SkepticalReview,
    build_skeptical_review,
)


class AgentTraceStep(TypedDict):
    """One role handoff in a coordinated report-analysis run."""

    sequence: int
    role: str
    status: str
    task: str
    output: str
    source_pages: list[int]


class AgentWorkflowRun(TypedDict):
    """Shared state produced by one bounded Agent workflow."""

    query: str
    route: RouteDecision
    metric_result: MetricToolResult | None
    results: list[SearchResult]
    answer: GroundedAnswer | None
    skeptical_review: SkepticalReview | None
    verification: VerificationResult | None
    trace: list[AgentTraceStep]


def _unique_pages(pages: list[int]) -> list[int]:
    """Return sorted positive PDF pages for compact audit display."""
    return sorted({page for page in pages if page >= 1})


def _trace_step(
    trace: list[AgentTraceStep],
    role: str,
    status: str,
    task: str,
    output: str,
    source_pages: list[int] | None = None,
) -> None:
    """Append a consistently numbered handoff to the shared trace."""
    trace.append(
        {
            "sequence": len(trace) + 1,
            "role": role,
            "status": status,
            "task": task,
            "output": output,
            "source_pages": _unique_pages(source_pages or []),
        }
    )


def run_agent_workflow(
    query: str,
    chunks: list[ReportChunk],
    route: RouteDecision,
    income_figures: IncomeStatementFigures | None = None,
    balance_figures: BalanceSheetFigures | None = None,
    existing_metric_result: MetricToolResult | None = None,
) -> AgentWorkflowRun:
    """Run routed tools and evidence agents through explicit handoffs."""
    if not query.strip():
        raise ValueError("A question is required.")

    trace: list[AgentTraceStep] = []
    _trace_step(
        trace=trace,
        role="Agent Router",
        status="completed",
        task="Select a bounded workflow and resource limits.",
        output=(
            f"Selected {route['label']} with up to {route['top_k']} "
            "retrieved passages."
        ),
    )

    metric_result = existing_metric_result
    if route["tool_name"] is not None:
        metric_reused = metric_result is not None
        if metric_result is None:
            metric_result = run_report_metric_tool(
                tool_name=route["tool_name"],
                income_figures=income_figures,
                balance_figures=balance_figures,
            )
        metric_page = (
            [metric_result["source_page"]]
            if metric_result["source_page"] is not None
            else []
        )
        _trace_step(
            trace=trace,
            role="Python Finance Tool",
            status=(
                "reused"
                if metric_reused
                else (
                    "completed"
                    if metric_result["is_available"]
                    else "unavailable"
                )
            ),
            task="Calculate the routed metric from extracted statements.",
            output=(
                f"{metric_result['label']}: "
                f"{metric_result['display_value']}"
                if metric_result["is_available"]
                else metric_result["messages"][0]
            ),
            source_pages=metric_page,
        )

    results = search_report_chunks(
        chunks=chunks,
        query=query,
        top_k=route["top_k"],
    )
    result_pages = [result["page_number"] for result in results]
    _trace_step(
        trace=trace,
        role="Evidence Retriever",
        status="completed" if results else "stopped",
        task="Find question-relevant passages while preserving PDF pages.",
        output=(
            f"Retrieved {len(results)} ranked passages."
            if results
            else "No matching report passage was found."
        ),
        source_pages=result_pages,
    )

    if not results:
        _trace_step(
            trace=trace,
            role="Agent Coordinator",
            status="stopped",
            task="Decide whether downstream Agents can continue.",
            output=(
                "The workflow stopped before drafting because no cited "
                "evidence was available."
            ),
        )
        return {
            "query": query,
            "route": route,
            "metric_result": metric_result,
            "results": [],
            "answer": None,
            "skeptical_review": None,
            "verification": None,
            "trace": trace,
        }

    answer = build_grounded_answer(
        query=query,
        results=results,
        max_evidence=route["max_evidence"],
    )
    answer_pages = [
        evidence["page_number"]
        for evidence in answer["evidence"]
    ]
    _trace_step(
        trace=trace,
        role="Analyst",
        status="completed" if answer["is_supported"] else "refused",
        task="Draft a conclusion using only retrieved report wording.",
        output=answer["conclusion"],
        source_pages=answer_pages,
    )

    skeptical_review = build_skeptical_review(
        query=query,
        answer=answer,
        results=results,
        max_challenges=route["max_challenges"],
    )
    challenge_pages = [
        challenge["page_number"]
        for challenge in skeptical_review["challenges"]
    ]
    _trace_step(
        trace=trace,
        role="Skeptic",
        status=skeptical_review["status"],
        task="Search retrieved evidence for relevant offsets and limits.",
        output=skeptical_review["summary"],
        source_pages=challenge_pages,
    )

    verification = verify_answer(
        query=query,
        answer=answer,
        skeptical_review=skeptical_review,
        results=results,
    )
    verification_pages = [
        *answer_pages,
        *challenge_pages,
    ]
    _trace_step(
        trace=trace,
        role="Verifier",
        status=verification["status"],
        task="Audit evidence thresholds, wording, citations, and disclosure.",
        output=verification["summary"],
        source_pages=verification_pages,
    )
    _trace_step(
        trace=trace,
        role="Agent Coordinator",
        status="completed",
        task="Finish the handoff chain without changing Agent outputs.",
        output=(
            f"Workflow completed with verifier status "
            f"{verification['status']}."
        ),
        source_pages=verification_pages,
    )

    return {
        "query": query,
        "route": route,
        "metric_result": metric_result,
        "results": results,
        "answer": answer,
        "skeptical_review": skeptical_review,
        "verification": verification,
        "trace": trace,
    }


def build_agent_audit_record(
    report_name: str,
    initial_route: RouteDecision,
    escalation: EscalationDecision,
    initial_run: AgentWorkflowRun,
    final_run: AgentWorkflowRun,
) -> dict[str, object]:
    """Build a compact JSON-ready record of routing, handoffs, and evidence."""
    answer = final_run["answer"]
    skeptical_review = final_run["skeptical_review"]
    verification = final_run["verification"]
    metric_result = final_run["metric_result"]

    cited_pages: list[int] = []
    if answer is not None:
        cited_pages.extend(
            item["page_number"] for item in answer["evidence"]
        )
    if skeptical_review is not None:
        cited_pages.extend(
            item["page_number"]
            for item in skeptical_review["challenges"]
        )
    if (
        metric_result is not None
        and metric_result["source_page"] is not None
    ):
        cited_pages.append(metric_result["source_page"])

    return {
        "schema_version": "1.0",
        "report_name": report_name,
        "query": final_run["query"],
        "initial_route": initial_route,
        "adaptive_escalation": {
            "escalated": escalation["escalated"],
            "summary": escalation["summary"],
            "signals": escalation["signals"],
            "final_route": escalation["route"],
        },
        "initial_agent_trace": initial_run["trace"],
        "final_agent_trace": final_run["trace"],
        "metric_result": metric_result,
        "answer": answer,
        "skeptical_review": skeptical_review,
        "verification": verification,
        "cited_pdf_pages": _unique_pages(cited_pages),
        "limitation": (
            "This deterministic audit record proves workflow provenance, "
            "not that the financial interpretation is complete or suitable "
            "for an investment decision."
        ),
    }
