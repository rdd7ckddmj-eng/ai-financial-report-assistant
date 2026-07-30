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

CHINESE_INCOME_STATEMENT_TEXT = """
贵州茅台酒股份有限公司2025年度合并利润表
单位：元 币种：人民币
项目 附注 2025年度 2024年度
一、营业总收入 168,838,102,514.79 170,899,152,276.34
其中：营业收入 168,838,102,514.79 170,899,152,276.34
五、净利润 82,330,000,000.00 86,240,000,000.00
归属于母公司股东的净利润 82,320,067,101.68 86,228,146,421.62
少数股东损益 9,932,898.32 11,853,578.38
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


def test_extract_chinese_a_share_income_statement_prefers_parent_profit() -> None:
    figures = extract_income_statement_figures(
        page_number=194,
        page_text=CHINESE_INCOME_STATEMENT_TEXT,
    )

    assert figures is not None
    assert figures["current_revenue"] == 168_838_102_514.79
    assert figures["previous_revenue"] == 170_899_152_276.34
    assert figures["current_net_profit"] == 82_320_067_101.68
    assert figures["previous_net_profit"] == 86_228_146_421.62
    assert figures["unit"] == "人民币元"
    assert figures["page_number"] == 194
    assert figures["current_period_weeks"] is None
    assert figures["previous_period_weeks"] is None


def test_extract_chinese_a_share_vertical_rows_preserves_loss_sign() -> None:
    page_text = """
    合并利润表
    单位：万元
    营业收入
    120,000.50
    110,000.25
    净利润
    （1,200.50）
    800.25
    """

    figures = extract_income_statement_figures(
        page_number=88,
        page_text=page_text,
    )

    assert figures is not None
    assert figures["current_revenue"] == 120_000.50
    assert figures["previous_revenue"] == 110_000.25
    assert figures["current_net_profit"] == -1_200.50
    assert figures["previous_net_profit"] == 800.25
    assert figures["unit"] == "万元"


def test_chinese_income_statement_does_not_guess_missing_profit() -> None:
    page_text = CHINESE_INCOME_STATEMENT_TEXT.replace(
        "五、净利润 82,330,000,000.00 86,240,000,000.00\n"
        "归属于母公司股东的净利润 "
        "82,320,067,101.68 86,228,146,421.62\n",
        "",
    )

    figures = extract_income_statement_figures(
        page_number=194,
        page_text=page_text,
    )

    assert figures is None
