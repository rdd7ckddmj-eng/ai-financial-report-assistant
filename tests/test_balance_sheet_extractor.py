from src.balance_sheet_extractor import (
    extract_balance_sheet_figures,
    find_balance_sheet_figures,
)


BALANCE_SHEET_TEXT = """
Non-current liabilities
Borrowings
(5,372)
(5,089)
(13,688)
(13,408)
Net assets
11,457
11,662
Equity
Group balance sheet
£m
Non-current assets
Property, plant and equipment
17,728
17,262
30,991
30,034
Current assets
Cash and cash equivalents
2,515
2,255
8,369
8,806
Non-current assets classified as held for sale
8
114
50
8,483
8,856
Current liabilities
Trade and other payables
(10,746)
(10,364)
(14,329)
(13,820)
Net current liabilities
(5,846)
(4,964)
"""


def test_extract_balance_sheet_figures_reconciles_current_totals() -> None:
    figures = extract_balance_sheet_figures(
        page_number=125,
        page_text=BALANCE_SHEET_TEXT,
    )

    assert figures is not None
    assert figures["current_assets_subtotal"] == 8_369
    assert figures["current_assets_held_for_sale"] == 114
    assert figures["current_resources"] == 8_483
    assert figures["current_liabilities"] == 14_329
    assert figures["current_net_current_liabilities"] == -5_846
    assert figures["previous_resources"] == 8_856
    assert figures["previous_liabilities"] == 13_820
    assert figures["previous_net_current_liabilities"] == -4_964
    assert figures["current_noncurrent_assets"] == 30_991
    assert figures["current_total_assets"] == 39_474
    assert figures["current_noncurrent_liabilities"] == 13_688
    assert figures["current_total_liabilities"] == 28_017
    assert figures["current_net_assets"] == 11_457
    assert figures["previous_total_assets"] == 38_890
    assert figures["previous_total_liabilities"] == 27_228
    assert figures["previous_net_assets"] == 11_662
    assert figures["unit"] == "£m"
    assert figures["page_number"] == 125


def test_extract_balance_sheet_figures_rejects_failed_reconciliation() -> None:
    page_text = BALANCE_SHEET_TEXT.replace("(5,846)", "(5,000)")

    figures = extract_balance_sheet_figures(
        page_number=125,
        page_text=page_text,
    )

    assert figures is None


def test_extract_balance_sheet_figures_rejects_unbalanced_totals() -> None:
    page_text = BALANCE_SHEET_TEXT.replace("11,457", "11,000")

    figures = extract_balance_sheet_figures(
        page_number=125,
        page_text=page_text,
    )

    assert figures is None


def test_find_balance_sheet_figures_scans_the_report() -> None:
    figures = find_balance_sheet_figures(
        [
            (1, "Annual report cover"),
            (123, "Group income statement"),
            (125, BALANCE_SHEET_TEXT),
        ]
    )

    assert figures is not None
    assert figures["page_number"] == 125


def test_extract_balance_sheet_figures_does_not_guess_other_pages() -> None:
    figures = extract_balance_sheet_figures(
        page_number=1,
        page_text="Annual report cover",
    )

    assert figures is None
