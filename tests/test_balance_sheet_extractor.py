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

CHINESE_BALANCE_SHEET_TEXT = """
贵州茅台酒股份有限公司2025年度合并资产负债表
单位：元 币种：人民币
项目 2025年12月31日 2024年12月31日
流动资产合计 90,000.50 80,000.25
非流动资产合计 210,000.50 200,000.75
资产总计 300,001.00 280,001.00
流动负债合计 50,000.25 45,000.50
非流动负债合计 30,000.75 25,000.50
负债合计 80,001.00 70,001.00
所有者权益（或股东权益）合计 220,000.00 210,000.00
负债和所有者权益（或股东权益）总计 300,001.00 280,001.00
"""

MIDEA_DUAL_BALANCE_SHEET_FIRST_PAGE = """
美的集团股份有限公司
合并及公司资产负债表
2025 年 12 月 31 日
(除特别注明外，金额单位为人民币千元)
资产 附注 2025 年 2024 年 2025 年 2024 年
合并 合并 公司 公司
流动资产合计 416,662,341 389,063,786 127,272,108 99,393,257
非流动资产合计 192,129,425 215,288,067 168,172,513 200,758,198
资产总计 608,791,766 604,351,853 295,444,621 300,151,455
"""

MIDEA_DUAL_BALANCE_SHEET_SECOND_PAGE = """
美的集团股份有限公司
合并及公司资产负债表(续)
(除特别注明外，金额单位为人民币千元)
合并 合并 公司 公司
流动负债合计 343,383,700 351,819,806 187,528,689 185,840,717
非流动负债合计 28,983,843 24,864,656 9,863,262 7,805,712
负债合计 372,367,543 376,684,462 197,391,951 193,646,429
股东权益合计 236,424,223 227,667,391 98,052,670 106,505,026
负债和股东权益总计 608,791,766 604,351,853 295,444,621 300,151,455
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
    assert figures["statement_format"] == "tesco_group"


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


def test_extract_chinese_a_share_balance_sheet_reconciles_totals() -> None:
    figures = extract_balance_sheet_figures(
        page_number=195,
        page_text=CHINESE_BALANCE_SHEET_TEXT,
    )

    assert figures is not None
    assert figures["current_assets_subtotal"] == 90_000.50
    assert figures["current_resources"] == 90_000.50
    assert figures["current_liabilities"] == 50_000.25
    assert figures["current_net_current_liabilities"] == 40_000.25
    assert figures["current_noncurrent_assets"] == 210_000.50
    assert figures["current_total_assets"] == 300_001.00
    assert figures["current_noncurrent_liabilities"] == 30_000.75
    assert figures["current_total_liabilities"] == 80_001.00
    assert figures["current_net_assets"] == 220_000.00
    assert figures["previous_total_assets"] == 280_001.00
    assert figures["previous_total_liabilities"] == 70_001.00
    assert figures["previous_net_assets"] == 210_000.00
    assert figures["current_assets_held_for_sale"] == 0
    assert figures["unit"] == "人民币元"
    assert figures["page_number"] == 195
    assert figures["statement_format"] == "chinese_a_share"


def test_extract_chinese_a_share_vertical_rows_and_chinese_commas() -> None:
    page_text = """
    合并资产负债表
    单位：万元
    流动资产合计
    14
    120，000
    110，000
    非流动资产合计
    180，000
    170，000
    资产总计
    300，000
    280，000
    流动负债合计
    100，000
    90，000
    非流动负债合计
    50，000
    50，000
    负债合计
    150，000
    140，000
    股东权益合计
    150，000
    140，000
    """

    figures = extract_balance_sheet_figures(
        page_number=96,
        page_text=page_text,
    )

    assert figures is not None
    assert figures["current_resources"] == 120_000
    assert figures["previous_resources"] == 110_000
    assert figures["current_liabilities"] == 100_000
    assert figures["previous_liabilities"] == 90_000
    assert figures["current_net_current_liabilities"] == 20_000
    assert figures["current_total_assets"] == 300_000
    assert figures["current_total_liabilities"] == 150_000
    assert figures["current_net_assets"] == 150_000
    assert figures["unit"] == "万元"


def test_chinese_balance_sheet_rejects_failed_equity_reconciliation() -> None:
    page_text = CHINESE_BALANCE_SHEET_TEXT.replace(
        "220,000.00 210,000.00",
        "219,000.00 210,000.00",
    )

    figures = extract_balance_sheet_figures(
        page_number=195,
        page_text=page_text,
    )

    assert figures is None


def test_chinese_balance_sheet_does_not_guess_parent_equity() -> None:
    page_text = CHINESE_BALANCE_SHEET_TEXT.replace(
        "所有者权益（或股东权益）合计 220,000.00 210,000.00",
        "归属于母公司所有者权益合计 219,000.00 209,000.00\n"
        "少数股东权益 1,000.00 1,000.00",
    )

    figures = extract_balance_sheet_figures(
        page_number=195,
        page_text=page_text,
    )

    assert figures is None


def test_find_chinese_balance_sheet_across_realistic_pages() -> None:
    figures = find_balance_sheet_figures(
        [
            (
                56,
                """
                合并资产负债表
                单位：元 币种：人民币
                流动资产合计
                252,518,662,398.57 251,726,674,636.66
                贵州茅台酒股份有限公司2025 年年度报告
                """,
            ),
            (
                57,
                """
                57 / 143
                非流动资产合计 51,316,181,622.87 47,217,905,282.04
                资产总计 303,834,844,021.44 298,944,579,918.70
                """,
            ),
            (
                58,
                """
                流动负债合计 49,610,476,817.81 56,515,990,618.96
                非流动负债合计 265,113,294.56 417,274,179.14
                负债合计 49,875,590,112.37 56,933,264,798.10
                所有者权益（或股东权
                贵州茅台酒股份有限公司2025 年年度报告
                """,
            ),
            (
                59,
                """
                59 / 143
                益）合计
                253,959,253,909.07 242,011,315,120.60
                负债和所有者权益（或股东权益）总计
                303,834,844,021.44 298,944,579,918.70
                母公司资产负债表
                """,
            ),
        ]
    )

    assert figures is not None
    assert figures["current_total_assets"] == 303_834_844_021.44
    assert figures["current_total_liabilities"] == 49_875_590_112.37
    assert figures["current_net_assets"] == 253_959_253_909.07
    assert figures["page_number"] == 56
    assert figures["end_page_number"] == 59


def test_find_dual_balance_sheet_uses_consolidated_columns() -> None:
    figures = find_balance_sheet_figures(
        [
            (131, MIDEA_DUAL_BALANCE_SHEET_FIRST_PAGE),
            (132, MIDEA_DUAL_BALANCE_SHEET_SECOND_PAGE),
        ]
    )

    assert figures is not None
    assert figures["current_resources"] == 416_662_341
    assert figures["previous_resources"] == 389_063_786
    assert figures["current_total_assets"] == 608_791_766
    assert figures["previous_total_assets"] == 604_351_853
    assert figures["current_total_liabilities"] == 372_367_543
    assert figures["previous_total_liabilities"] == 376_684_462
    assert figures["current_net_assets"] == 236_424_223
    assert figures["previous_net_assets"] == 227_667_391
    assert figures["unit"] == "人民币千元"
    assert figures["page_number"] == 131
    assert figures["end_page_number"] == 132


def test_dual_balance_sheet_ignores_trailing_pdf_page_number() -> None:
    first_page = MIDEA_DUAL_BALANCE_SHEET_FIRST_PAGE.replace(
        "资产总计 608,791,766 604,351,853 295,444,621 300,151,455",
        "资产总计\n"
        "608,791,766\n"
        "604,351,853\n"
        "295,444,621\n"
        "300,151,455\n"
        "132",
    )

    figures = find_balance_sheet_figures(
        [
            (131, first_page),
            (132, MIDEA_DUAL_BALANCE_SHEET_SECOND_PAGE),
        ]
    )

    assert figures is not None
    assert figures["current_total_assets"] == 608_791_766
    assert figures["previous_total_assets"] == 604_351_853
    assert figures["current_total_liabilities"] == 372_367_543
    assert figures["unit"] == "人民币千元"
