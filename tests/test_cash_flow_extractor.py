from src.cash_flow_extractor import (
    extract_cash_flow_figures,
    find_cash_flow_figures,
)


CASH_FLOW_TEXT = """
Group cash flow statement
53 weeks
ended
52 weeks
ended
£m
Net cash generated from/(used in) operating activities
3,906
2,919
Net cash generated from/(used in) investing activities
(706)
(441)
Net cash generated from/(used in) financing activities
(3,086)
(2,940)
Net increase/(decrease) in cash and cash equivalents
114
(462)
Cash and cash equivalents at the beginning of the year
1,399
1,874
Effect of foreign exchange rate changes
(2)
(13)
Cash and cash equivalents at the end of the year
19
1,511
1,399
"""


def test_extract_cash_flow_figures_reconciles_both_cash_movements() -> None:
    figures = extract_cash_flow_figures(
        page_number=128,
        page_text=CASH_FLOW_TEXT,
    )

    assert figures is not None
    assert figures["current_operating_cash_flow"] == 3_906
    assert figures["current_investing_cash_flow"] == -706
    assert figures["current_financing_cash_flow"] == -3_086
    assert figures["current_net_cash_change"] == 114
    assert figures["current_opening_cash"] == 1_399
    assert figures["current_exchange_effect"] == -2
    assert figures["current_ending_cash"] == 1_511
    assert figures["previous_ending_cash"] == 1_399
    assert figures["current_period_weeks"] == 53
    assert figures["previous_period_weeks"] == 52
    assert figures["unit"] == "£m"
    assert figures["page_number"] == 128


def test_extract_cash_flow_figures_rejects_section_mismatch() -> None:
    page_text = CASH_FLOW_TEXT.replace("114\n(462)", "100\n(462)")

    figures = extract_cash_flow_figures(
        page_number=128,
        page_text=page_text,
    )

    assert figures is None


def test_extract_cash_flow_figures_rejects_ending_cash_mismatch() -> None:
    page_text = CASH_FLOW_TEXT.replace("1,511\n1,399", "1,500\n1,399")

    figures = extract_cash_flow_figures(
        page_number=128,
        page_text=page_text,
    )

    assert figures is None


def test_find_cash_flow_figures_scans_the_report() -> None:
    figures = find_cash_flow_figures(
        [
            (1, "Annual report cover"),
            (125, "Group balance sheet"),
            (128, CASH_FLOW_TEXT),
        ]
    )

    assert figures is not None
    assert figures["page_number"] == 128


def test_extract_cash_flow_figures_does_not_guess_other_pages() -> None:
    figures = extract_cash_flow_figures(
        page_number=1,
        page_text="Annual report cover",
    )

    assert figures is None
