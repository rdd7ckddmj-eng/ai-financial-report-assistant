from pathlib import Path

import pytest

from src.qa_benchmark import (
    DEFAULT_BENCHMARK_PATH,
    DEFAULT_REPORT_PATH,
    load_benchmark_cases,
    run_default_benchmark,
)


def test_benchmark_csv_has_unique_auditable_cases() -> None:
    cases = load_benchmark_cases(DEFAULT_BENCHMARK_PATH)

    assert len(cases) == 10
    assert len({case["case_id"] for case in cases}) == 10
    assert all(case["question"] for case in cases)
    assert all(case["notes"] for case in cases)


def test_benchmark_loader_rejects_invalid_boolean(tmp_path: Path) -> None:
    benchmark_path = tmp_path / "invalid.csv"
    benchmark_path.write_text(
        "case_id,question,expected_mode,expected_tool,expected_metric,"
        "expected_metric_page,required_retrieval_page,expected_concept,"
        "expected_supported,expected_escalated,expected_has_challenge,"
        "required_challenge_page,expected_verification,notes\n"
        "bad,Question?,quick_evidence,none,none,,,none,maybe,false,"
        "false,,approved,Invalid boolean\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Expected true or false"):
        load_benchmark_cases(benchmark_path)


def test_real_report_qa_baseline_is_measured_not_assumed() -> None:
    if not DEFAULT_REPORT_PATH.exists():
        pytest.skip("The public Tesco PDF is stored locally and not committed.")

    results, summary = run_default_benchmark()

    assert summary["passed_cases"] == 10
    assert summary["total_cases"] == 10
    assert summary["case_pass_rate"] == pytest.approx(1.0)
    assert summary["check_pass_rate"] == pytest.approx(1.0)
    assert summary["route_accuracy"] == pytest.approx(1.0)
    assert summary["retrieval_page_hit_rate"] == pytest.approx(1.0)
    assert summary["metric_accuracy"] == pytest.approx(1.0)
    assert summary["escalation_accuracy"] == pytest.approx(1.0)
    assert summary["safe_refusal_accuracy"] == pytest.approx(1.0)
    failed_cases = [
        result["case_id"]
        for result in results
        if not result["passed"]
    ]
    assert failed_cases == []
