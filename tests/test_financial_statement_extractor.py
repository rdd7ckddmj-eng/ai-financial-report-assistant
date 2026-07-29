from src.financial_statement_extractor import (
    extract_income_statement_figures,
    find_income_statement_figures,
)


INCOME_STATEMENT_TEXT = """
Group income statement
53 weeks ended
52 weeks ended
£m
Revenue
2,3
73,712
-
73,712
69,916
-
69,916
Cost of sales
Profit/(loss) for the year
1,940
(153)
1,787
1,989
(359)
1,630
Attributable to:
"""


def test_extract_income_statement_figures_uses_total_columns() -> None:
    figures = extract_income_statement_figures(
        page_number=123,
        page_text=INCOME_STATEMENT_TEXT,
    )

    assert figures is not None
    assert figures["current_revenue"] == 73_712
    assert figures["previous_revenue"] == 69_916
    assert figures["current_net_profit"] == 1_787
    assert figures["previous_net_profit"] == 1_630
    assert figures["unit"] == "£m"
    assert figures["page_number"] == 123
    assert figures["current_period_weeks"] == 53
    assert figures["previous_period_weeks"] == 52


def test_extract_income_statement_figures_preserves_loss_sign() -> None:
    page_text = INCOME_STATEMENT_TEXT.replace(
        "1,940\n(153)\n1,787",
        "(8)\n(2)\n(10)",
    )

    figures = extract_income_statement_figures(
        page_number=10,
        page_text=page_text,
    )

    assert figures is not None
    assert figures["current_net_profit"] == -10


def test_extract_income_statement_figures_does_not_guess_other_pages() -> None:
    figures = extract_income_statement_figures(
        page_number=1,
        page_text="Annual report cover page",
    )

    assert figures is None


def test_find_income_statement_figures_scans_the_report() -> None:
    figures = find_income_statement_figures(
        [
            (1, "Annual report cover page"),
            (50, "Strategic report"),
            (123, INCOME_STATEMENT_TEXT),
        ]
    )

    assert figures is not None
    assert figures["page_number"] == 123
    assert figures["current_revenue"] == 73_712


def test_extract_income_statement_figures_allows_missing_week_counts() -> None:
    page_text = INCOME_STATEMENT_TEXT.replace(
        "53 weeks ended\n52 weeks ended\n",
        "Year ended\nPrior year ended\n",
    )

    figures = extract_income_statement_figures(
        page_number=123,
        page_text=page_text,
    )

    assert figures is not None
    assert figures["current_period_weeks"] is None
    assert figures["previous_period_weeks"] is None
