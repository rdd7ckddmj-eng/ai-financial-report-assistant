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

CHINESE_CASH_FLOW_TEXT = """
贵州茅台酒股份有限公司2025年度合并现金流量表
单位：元 币种：人民币
项目 2025年度 2024年度
经营活动产生的现金流量净额 10,000.00 9,000.00
投资活动产生的现金流量净额 （4,000.00） （3,000.00）
筹资活动产生的现金流量净额 （2,000.00） （4,000.00）
四、汇率变动对现金及现金等价物的影响 100.00 （100.00）
五、现金及现金等价物净增加额 4,100.00 1,900.00
加：期初现金及现金等价物余额 20,000.00 18,100.00
六、期末现金及现金等价物余额 24,100.00 20,000.00
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
    assert figures["statement_format"] == "tesco_group"


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


def test_extract_chinese_a_share_cash_flow_reconciles_exchange_once() -> None:
    figures = extract_cash_flow_figures(
        page_number=197,
        page_text=CHINESE_CASH_FLOW_TEXT,
    )

    assert figures is not None
    assert figures["current_operating_cash_flow"] == 10_000
    assert figures["current_investing_cash_flow"] == -4_000
    assert figures["current_financing_cash_flow"] == -2_000
    assert figures["current_exchange_effect"] == 100
    assert figures["current_net_cash_change"] == 4_100
    assert figures["current_opening_cash"] == 20_000
    assert figures["current_ending_cash"] == 24_100
    assert figures["previous_exchange_effect"] == -100
    assert figures["previous_net_cash_change"] == 1_900
    assert figures["previous_ending_cash"] == 20_000
    assert figures["current_period_weeks"] is None
    assert figures["previous_period_weeks"] is None
    assert figures["unit"] == "人民币元"
    assert figures["page_number"] == 197
    assert figures["statement_format"] == "chinese_a_share"


def test_extract_chinese_a_share_vertical_rows_and_chinese_commas() -> None:
    page_text = """
    合并现金流量表
    单位：万元
    经营活动产生的现金流量净额
    45
    10，000
    9，000
    投资活动产生的现金流量净额
    （4，000）
    （3，000）
    筹资活动产生的现金流量净额
    （2，000）
    （4，000）
    汇率变动对现金及现金等价物的影响
    100
    （100）
    现金及现金等价物净增加额
    4，100
    1，900
    期初现金及现金等价物余额
    20，000
    18，100
    期末现金及现金等价物余额
    24，100
    20，000
    """

    figures = extract_cash_flow_figures(
        page_number=98,
        page_text=page_text,
    )

    assert figures is not None
    assert figures["current_operating_cash_flow"] == 10_000
    assert figures["current_investing_cash_flow"] == -4_000
    assert figures["current_net_cash_change"] == 4_100
    assert figures["current_ending_cash"] == 24_100
    assert figures["unit"] == "万元"


def test_chinese_cash_flow_rejects_section_mismatch() -> None:
    page_text = CHINESE_CASH_FLOW_TEXT.replace(
        "4,100.00 1,900.00",
        "4,000.00 1,900.00",
    )

    figures = extract_cash_flow_figures(
        page_number=197,
        page_text=page_text,
    )

    assert figures is None


def test_chinese_cash_flow_rejects_ending_cash_mismatch() -> None:
    page_text = CHINESE_CASH_FLOW_TEXT.replace(
        "24,100.00 20,000.00",
        "24,000.00 20,000.00",
    )

    figures = extract_cash_flow_figures(
        page_number=197,
        page_text=page_text,
    )

    assert figures is None
