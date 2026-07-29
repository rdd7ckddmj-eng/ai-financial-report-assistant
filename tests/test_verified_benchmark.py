import csv
from pathlib import Path

import pytest

from src.balance_sheet_extractor import find_balance_sheet_figures
from src.cash_flow_extractor import find_cash_flow_figures
from src.financial_statement_extractor import find_income_statement_figures
from src.pdf_extractor import extract_pdf_pages


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_PATH = (
    PROJECT_ROOT / "data" / "verified" / "tesco_2026_key_figures.csv"
)
REPORT_PATH = (
    PROJECT_ROOT / "data" / "reports" / "tesco_annual_report_2026.pdf"
)


def load_benchmark() -> list[dict[str, str]]:
    """Load the human-verified answer key used by the extraction tests."""
    with BENCHMARK_PATH.open(encoding="utf-8", newline="") as benchmark_file:
        return list(csv.DictReader(benchmark_file))


def test_verified_benchmark_has_complete_unique_rows() -> None:
    rows = load_benchmark()
    metric_keys = [row["metric_key"] for row in rows]

    assert len(rows) == 20
    assert len(metric_keys) == len(set(metric_keys))
    assert all(row["verification_status"] == "Verified" for row in rows)
    assert all(row["source_pdf_page"] for row in rows)
    assert all(row["source_row"] for row in rows)


def test_real_report_extraction_matches_verified_benchmark() -> None:
    if not REPORT_PATH.exists():
        pytest.skip("The public Tesco PDF is stored locally and not committed.")

    pages = extract_pdf_pages(REPORT_PATH.read_bytes())
    page_pairs = [
        (page["page_number"], page["text"])
        for page in pages
    ]
    income = find_income_statement_figures(page_pairs)
    balance = find_balance_sheet_figures(page_pairs)
    cash_flow = find_cash_flow_figures(page_pairs)

    assert income is not None
    assert balance is not None
    assert cash_flow is not None

    actual = {
        "revenue": (
            income["current_revenue"],
            income["previous_revenue"],
            income["unit"],
            income["page_number"],
        ),
        "net_profit": (
            income["current_net_profit"],
            income["previous_net_profit"],
            income["unit"],
            income["page_number"],
        ),
        "current_assets_subtotal": (
            balance["current_assets_subtotal"],
            balance["previous_assets_subtotal"],
            balance["unit"],
            balance["page_number"],
        ),
        "assets_held_for_sale": (
            balance["current_assets_held_for_sale"],
            balance["previous_assets_held_for_sale"],
            balance["unit"],
            balance["page_number"],
        ),
        "current_resources": (
            balance["current_resources"],
            balance["previous_resources"],
            balance["unit"],
            balance["page_number"],
        ),
        "current_liabilities": (
            balance["current_liabilities"],
            balance["previous_liabilities"],
            balance["unit"],
            balance["page_number"],
        ),
        "net_current_liabilities": (
            balance["current_net_current_liabilities"],
            balance["previous_net_current_liabilities"],
            balance["unit"],
            balance["page_number"],
        ),
        "noncurrent_assets": (
            balance["current_noncurrent_assets"],
            balance["previous_noncurrent_assets"],
            balance["unit"],
            balance["page_number"],
        ),
        "total_assets": (
            balance["current_total_assets"],
            balance["previous_total_assets"],
            balance["unit"],
            balance["page_number"],
        ),
        "noncurrent_liabilities": (
            balance["current_noncurrent_liabilities"],
            balance["previous_noncurrent_liabilities"],
            balance["unit"],
            balance["page_number"],
        ),
        "total_liabilities": (
            balance["current_total_liabilities"],
            balance["previous_total_liabilities"],
            balance["unit"],
            balance["page_number"],
        ),
        "net_assets": (
            balance["current_net_assets"],
            balance["previous_net_assets"],
            balance["unit"],
            balance["page_number"],
        ),
        "operating_cash_flow": (
            cash_flow["current_operating_cash_flow"],
            cash_flow["previous_operating_cash_flow"],
            cash_flow["unit"],
            cash_flow["page_number"],
        ),
        "investing_cash_flow": (
            cash_flow["current_investing_cash_flow"],
            cash_flow["previous_investing_cash_flow"],
            cash_flow["unit"],
            cash_flow["page_number"],
        ),
        "financing_cash_flow": (
            cash_flow["current_financing_cash_flow"],
            cash_flow["previous_financing_cash_flow"],
            cash_flow["unit"],
            cash_flow["page_number"],
        ),
        "net_cash_change": (
            cash_flow["current_net_cash_change"],
            cash_flow["previous_net_cash_change"],
            cash_flow["unit"],
            cash_flow["page_number"],
        ),
        "opening_cash": (
            cash_flow["current_opening_cash"],
            cash_flow["previous_opening_cash"],
            cash_flow["unit"],
            cash_flow["page_number"],
        ),
        "exchange_effect": (
            cash_flow["current_exchange_effect"],
            cash_flow["previous_exchange_effect"],
            cash_flow["unit"],
            cash_flow["page_number"],
        ),
        "ending_cash": (
            cash_flow["current_ending_cash"],
            cash_flow["previous_ending_cash"],
            cash_flow["unit"],
            cash_flow["page_number"],
        ),
        "reporting_period_weeks": (
            income["current_period_weeks"],
            income["previous_period_weeks"],
            "weeks",
            income["page_number"],
        ),
    }

    for row in load_benchmark():
        current, previous, unit, page_number = actual[row["metric_key"]]
        assert current == float(row["current_value"])
        assert previous == float(row["previous_value"])
        assert unit == row["unit"]
        assert page_number == int(row["source_pdf_page"])
