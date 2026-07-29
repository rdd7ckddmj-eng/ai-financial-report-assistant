"""Evaluate report Q&A behavior against human-defined expected outcomes."""

import csv
import json
from pathlib import Path
from typing import TypedDict

from src.adaptive_escalation import decide_adaptive_escalation
from src.agent_coordinator import run_agent_workflow
from src.agent_router import route_question
from src.balance_sheet_extractor import (
    BalanceSheetFigures,
    find_balance_sheet_figures,
)
from src.financial_statement_extractor import (
    IncomeStatementFigures,
    find_income_statement_figures,
)
from src.pdf_extractor import extract_pdf_pages
from src.report_retriever import ReportChunk, chunk_report_pages


class BenchmarkCase(TypedDict):
    """One human-defined question and its expected system behavior."""

    case_id: str
    question: str
    expected_mode: str
    expected_tool: str | None
    expected_metric: str | None
    expected_metric_page: int | None
    required_retrieval_page: int | None
    expected_concept: str | None
    expected_supported: bool
    expected_escalated: bool
    expected_has_challenge: bool
    required_challenge_page: int | None
    expected_verification: str | None
    notes: str


class BenchmarkCheck(TypedDict):
    """One expected-versus-actual comparison."""

    name: str
    passed: bool
    expected: object
    actual: object


class BenchmarkCaseResult(TypedDict):
    """All checks for one benchmark question."""

    case_id: str
    question: str
    passed: bool
    checks: list[BenchmarkCheck]
    notes: str


class BenchmarkSummary(TypedDict):
    """Portfolio-level quality measures across benchmark cases."""

    total_cases: int
    passed_cases: int
    case_pass_rate: float
    total_checks: int
    passed_checks: int
    check_pass_rate: float
    route_accuracy: float
    retrieval_page_hit_rate: float
    metric_accuracy: float
    escalation_accuracy: float
    safe_refusal_accuracy: float


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BENCHMARK_PATH = (
    PROJECT_ROOT / "data" / "verified" / "tesco_qa_benchmark.csv"
)
DEFAULT_REPORT_PATH = (
    PROJECT_ROOT / "data" / "reports" / "tesco_annual_report_2026.pdf"
)


def _optional_text(value: str) -> str | None:
    """Treat blank and explicit 'none' cells as absent expectations."""
    cleaned = value.strip()
    return None if not cleaned or cleaned.lower() == "none" else cleaned


def _optional_int(value: str) -> int | None:
    """Parse an optional positive PDF page."""
    cleaned = value.strip()
    return int(cleaned) if cleaned else None


def _parse_bool(value: str) -> bool:
    """Parse a strict human-readable CSV boolean."""
    cleaned = value.strip().lower()
    if cleaned not in {"true", "false"}:
        raise ValueError(f"Expected true or false, received: {value}.")
    return cleaned == "true"


def load_benchmark_cases(
    path: Path = DEFAULT_BENCHMARK_PATH,
) -> list[BenchmarkCase]:
    """Load the auditable CSV benchmark without hidden defaults."""
    with path.open(encoding="utf-8", newline="") as benchmark_file:
        rows = list(csv.DictReader(benchmark_file))

    cases: list[BenchmarkCase] = []
    seen_ids: set[str] = set()
    for row in rows:
        case_id = row["case_id"].strip()
        if not case_id:
            raise ValueError("Every benchmark case requires a case_id.")
        if case_id in seen_ids:
            raise ValueError(f"Duplicate benchmark case_id: {case_id}.")

        cases.append(
            {
                "case_id": case_id,
                "question": row["question"].strip(),
                "expected_mode": row["expected_mode"].strip(),
                "expected_tool": _optional_text(row["expected_tool"]),
                "expected_metric": _optional_text(row["expected_metric"]),
                "expected_metric_page": _optional_int(
                    row["expected_metric_page"]
                ),
                "required_retrieval_page": _optional_int(
                    row["required_retrieval_page"]
                ),
                "expected_concept": _optional_text(
                    row["expected_concept"]
                ),
                "expected_supported": _parse_bool(
                    row["expected_supported"]
                ),
                "expected_escalated": _parse_bool(
                    row["expected_escalated"]
                ),
                "expected_has_challenge": _parse_bool(
                    row["expected_has_challenge"]
                ),
                "required_challenge_page": _optional_int(
                    row["required_challenge_page"]
                ),
                "expected_verification": _optional_text(
                    row["expected_verification"]
                ),
                "notes": row["notes"].strip(),
            }
        )
        seen_ids.add(case_id)

    return cases


def _add_check(
    checks: list[BenchmarkCheck],
    name: str,
    expected: object,
    actual: object,
) -> None:
    """Append one exact comparison so failures remain explainable."""
    checks.append(
        {
            "name": name,
            "passed": expected == actual,
            "expected": expected,
            "actual": actual,
        }
    )


def evaluate_benchmark_case(
    case: BenchmarkCase,
    chunks: list[ReportChunk],
    income_figures: IncomeStatementFigures | None,
    balance_figures: BalanceSheetFigures | None,
) -> BenchmarkCaseResult:
    """Run the real Agent workflow and compare it with one expected case."""
    route = route_question(case["question"])
    initial_run = run_agent_workflow(
        query=case["question"],
        chunks=chunks,
        route=route,
        income_figures=income_figures,
        balance_figures=balance_figures,
    )
    metric_result = initial_run["metric_result"]
    escalation = decide_adaptive_escalation(
        current_route=route,
        answer=initial_run["answer"],
        skeptical_review=initial_run["skeptical_review"],
        verification=initial_run["verification"],
        results=initial_run["results"],
        metric_available=(
            metric_result["is_available"]
            if metric_result is not None
            else None
        ),
    )
    final_run = (
        run_agent_workflow(
            query=case["question"],
            chunks=chunks,
            route=escalation["route"],
            income_figures=income_figures,
            balance_figures=balance_figures,
            existing_metric_result=metric_result,
        )
        if escalation["escalated"]
        else initial_run
    )

    final_metric = final_run["metric_result"]
    answer = final_run["answer"]
    skeptical_review = final_run["skeptical_review"]
    verification = final_run["verification"]
    retrieval_pages = sorted(
        {result["page_number"] for result in final_run["results"]}
    )
    concepts = answer["concepts"] if answer is not None else []
    challenge_pages = sorted(
        {
            challenge["page_number"]
            for challenge in (
                skeptical_review["challenges"]
                if skeptical_review is not None
                else []
            )
        }
    )

    checks: list[BenchmarkCheck] = []
    _add_check(
        checks,
        "route_mode",
        case["expected_mode"],
        route["mode"],
    )
    _add_check(
        checks,
        "tool_selection",
        case["expected_tool"],
        route["tool_name"],
    )

    if case["expected_metric"] is not None:
        _add_check(
            checks,
            "metric_output",
            case["expected_metric"],
            (
                final_metric["display_value"]
                if final_metric is not None
                else None
            ),
        )
        _add_check(
            checks,
            "metric_source_page",
            case["expected_metric_page"],
            (
                final_metric["source_page"]
                if final_metric is not None
                else None
            ),
        )

    if case["required_retrieval_page"] is not None:
        required_page = case["required_retrieval_page"]
        _add_check(
            checks,
            "retrieval_page",
            True,
            required_page in retrieval_pages,
        )

    _add_check(
        checks,
        "financial_concept",
        (
            []
            if case["expected_concept"] is None
            else [case["expected_concept"]]
        ),
        concepts,
    )
    _add_check(
        checks,
        (
            "safe_refusal"
            if not case["expected_supported"]
            else "support_decision"
        ),
        case["expected_supported"],
        answer["is_supported"] if answer is not None else False,
    )
    _add_check(
        checks,
        "adaptive_escalation",
        case["expected_escalated"],
        escalation["escalated"],
    )
    _add_check(
        checks,
        "challenge_presence",
        case["expected_has_challenge"],
        bool(challenge_pages),
    )

    if case["required_challenge_page"] is not None:
        required_challenge_page = case["required_challenge_page"]
        _add_check(
            checks,
            "challenge_page",
            True,
            required_challenge_page in challenge_pages,
        )

    _add_check(
        checks,
        "verification_status",
        case["expected_verification"],
        verification["status"] if verification is not None else None,
    )

    return {
        "case_id": case["case_id"],
        "question": case["question"],
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
        "notes": case["notes"],
    }


def evaluate_benchmark(
    cases: list[BenchmarkCase],
    chunks: list[ReportChunk],
    income_figures: IncomeStatementFigures | None,
    balance_figures: BalanceSheetFigures | None,
) -> list[BenchmarkCaseResult]:
    """Evaluate every benchmark case with the same product workflow."""
    return [
        evaluate_benchmark_case(
            case=case,
            chunks=chunks,
            income_figures=income_figures,
            balance_figures=balance_figures,
        )
        for case in cases
    ]


def _check_rate(
    results: list[BenchmarkCaseResult],
    names: set[str],
) -> float:
    """Calculate the pass rate for selected check names."""
    selected = [
        check
        for result in results
        for check in result["checks"]
        if check["name"] in names
    ]
    if not selected:
        return 0.0
    return sum(check["passed"] for check in selected) / len(selected)


def summarise_benchmark(
    results: list[BenchmarkCaseResult],
) -> BenchmarkSummary:
    """Return high-level quality rates without concealing failed cases."""
    all_checks = [
        check
        for result in results
        for check in result["checks"]
    ]
    total_cases = len(results)
    passed_cases = sum(result["passed"] for result in results)
    total_checks = len(all_checks)
    passed_checks = sum(check["passed"] for check in all_checks)

    return {
        "total_cases": total_cases,
        "passed_cases": passed_cases,
        "case_pass_rate": (
            passed_cases / total_cases if total_cases else 0.0
        ),
        "total_checks": total_checks,
        "passed_checks": passed_checks,
        "check_pass_rate": (
            passed_checks / total_checks if total_checks else 0.0
        ),
        "route_accuracy": _check_rate(results, {"route_mode"}),
        "retrieval_page_hit_rate": _check_rate(
            results,
            {"retrieval_page"},
        ),
        "metric_accuracy": _check_rate(results, {"metric_output"}),
        "escalation_accuracy": _check_rate(
            results,
            {"adaptive_escalation"},
        ),
        "safe_refusal_accuracy": _check_rate(
            results,
            {"safe_refusal"},
        ),
    }


def run_default_benchmark() -> tuple[
    list[BenchmarkCaseResult],
    BenchmarkSummary,
]:
    """Run the local Tesco benchmark used by tests and the product UI."""
    pages = extract_pdf_pages(DEFAULT_REPORT_PATH.read_bytes())
    chunks = chunk_report_pages(pages)
    income_figures = find_income_statement_figures(
        (page["page_number"], page["text"]) for page in pages
    )
    balance_figures = find_balance_sheet_figures(
        (page["page_number"], page["text"]) for page in pages
    )
    results = evaluate_benchmark(
        cases=load_benchmark_cases(),
        chunks=chunks,
        income_figures=income_figures,
        balance_figures=balance_figures,
    )
    return results, summarise_benchmark(results)


def main() -> None:
    """Print a JSON quality report for local or CI use."""
    results, summary = run_default_benchmark()
    failed_cases = [
        result for result in results if not result["passed"]
    ]
    print(
        json.dumps(
            {
                "summary": summary,
                "failed_cases": failed_cases,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
