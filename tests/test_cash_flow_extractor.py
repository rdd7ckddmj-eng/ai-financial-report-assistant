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

MIDEA_DUAL_CASH_FLOW_TEXT = """
美的集团股份有限公司
2025 年度合并及公司现金流量表
(除特别注明外，金额单位为人民币千元)
项目 附注 2025 年度 2024 年度 2025 年度 2024 年度
合并 合并 公司 公司
一、经营活动产生/(使用)的现金流量
经营活动产生/(使用)的现金流量净额 四(64)(h) 53,345,930 60,511,572 (11,628,058) 4,645,875
二、投资活动产生/(使用)的现金流量
投资活动产生/(使用)的现金流量净额 25,340,273 (87,901,802) 61,045,937 (32,782,384)
三、筹资活动(使用)/产生的现金流量
筹资活动(使用)/产生的现金流量净额 (64,957,779) 22,697,954 (37,445,961) 5,736,041
四、汇率变动对现金及现金等价物的影响 (338,482) (76,256) - -
五、现金及现金等价物净增加/(减少)额 四(64)(h) 13,389,942 (4,768,532) 11,971,918 (22,400,468)
加：年初现金及现金等价物余额 55,118,728 59,887,260 6,882,690 29,283,158
六、年末现金及现金等价物余额 四(64)(i) 68,508,670 55,118,728 18,854,608 6,882,690
"""

MIDEA_2024_DUAL_CASH_FLOW_TEXT = """
美的集团股份有限公司
2024 年度合并及公司现金流量表
(除特别注明外，金额单位为人民币千元)
项目 附注 2024 年度 2023 年度 2024 年度 2023 年度
合并 合并 公司 公司
一、经营活动产生的现金流量
经营活动产生的现金流量净额 四(65)(h) 60,511,572 57,902,611 4,645,875 17,516,442
二、投资活动使用的现金流量
投资活动使用的现金流量净额 (87,901,802) (31,219,855) (32,782,384) (423,659)
三、筹资活动使用的现金流量
筹资活动产生/(使用)的现金流量净额 22,697,954 (17,910,213) 5,736,041 (15,713,854)
四、汇率变动对现金及现金等价物的影响 (76,256) (17,251) - -
五、现金及现金等价物净(减少)/增加额 四(65)(h) (4,768,532) 8,755,292 (22,400,468) 1,378,929
加：年初现金及现金等价物余额 59,887,260 51,131,968 29,283,158 27,904,229
六、年末现金及现金等价物余额 四(65)(i) 55,118,728 59,887,260 6,882,690 29,283,158
"""

MIDEA_2023_DUAL_CASH_FLOW_TEXT = """
美的集团股份有限公司
2023 年度合并及公司现金流量表
(除特别注明外，金额单位为人民币千元)
项目 附注 2023 年度 2022 年度 2023 年度 2022 年度
合并 合并 公司 公司
一、经营活动产生的现金流量
经营活动产生的现金流量净额 四(63)(h) 57,902,611 34,657,828 17,516,442 14,946,438
二、投资活动使用的现金流量
投资活动使用的现金流量净额 (31,219,855) (13,509,510) (423,659) (1,649,661)
三、筹资活动使用的现金流量
筹资活动使用的现金流量净额 (17,910,213) (10,854,881) (15,713,854) (7,349,590)
四、汇率变动对现金及现金等价物的影响 (17,251) 288,492 - -
五、现金及现金等价物净增加额 四(63)(h) 8,755,292 10,581,929 1,378,929 5,947,187
加：年初现金及现金等价物余额 51,131,968 40,550,039 27,904,229 21,957,042
六、年末现金及现金等价物余额 四(63)(i) 59,887,260 51,131,968 29,283,158 27,904,229
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


def test_find_chinese_cash_flow_across_realistic_pages() -> None:
    figures = find_cash_flow_figures(
        [
            (
                64,
                """
                合并现金流量表
                2025 年 1—12 月
                单位：元 币种：人民币
                """,
            ),
            (
                65,
                """
                经营活动产生的现金流
                量净额
                61,522,204,989.35 92,463,692,168.43
                投资活动产生的现金流
                量净额
                -31,641,898,948.89 -1,785,202,630.71
                贵州茅台酒股份有限公司2025 年年度报告
                """,
            ),
            (
                66,
                """
                66 / 143
                筹资活动产生的现金流
                量净额
                -73,427,081,208.87 -71,067,506,484.81
                四、汇率变动对现金及现金等价
                物的影响
                2,295,358.30 -1,082,747.55
                五、现金及现金等价物净增加额
                -43,544,479,810.11 19,609,900,305.36
                加：期初现金及现金等价物余
                额
                169,970,089,257.83 150,360,188,952.47
                六、期末现金及现金等价物余额
                126,425,609,447.72 169,970,089,257.83
                母公司现金流量表
                """,
            ),
        ]
    )

    assert figures is not None
    assert figures["current_operating_cash_flow"] == 61_522_204_989.35
    assert figures["current_net_cash_change"] == -43_544_479_810.11
    assert figures["current_ending_cash"] == 126_425_609_447.72
    assert figures["page_number"] == 64
    assert figures["end_page_number"] == 66


def test_extract_dual_cash_flow_uses_consolidated_columns() -> None:
    figures = extract_cash_flow_figures(
        page_number=136,
        page_text=MIDEA_DUAL_CASH_FLOW_TEXT,
    )

    assert figures is not None
    assert figures["current_operating_cash_flow"] == 53_345_930
    assert figures["previous_operating_cash_flow"] == 60_511_572
    assert figures["current_investing_cash_flow"] == 25_340_273
    assert figures["current_financing_cash_flow"] == -64_957_779
    assert figures["current_exchange_effect"] == -338_482
    assert figures["current_net_cash_change"] == 13_389_942
    assert figures["current_ending_cash"] == 68_508_670
    assert figures["unit"] == "人民币千元"


def test_extract_midea_2024_cash_flow_label_variants() -> None:
    figures = extract_cash_flow_figures(
        page_number=160,
        page_text=MIDEA_2024_DUAL_CASH_FLOW_TEXT,
    )

    assert figures is not None
    assert figures["current_operating_cash_flow"] == 60_511_572
    assert figures["previous_operating_cash_flow"] == 57_902_611
    assert figures["current_investing_cash_flow"] == -87_901_802
    assert figures["current_financing_cash_flow"] == 22_697_954
    assert figures["current_exchange_effect"] == -76_256
    assert figures["current_net_cash_change"] == -4_768_532
    assert figures["current_ending_cash"] == 55_118_728
    assert figures["previous_ending_cash"] == 59_887_260
    assert figures["unit"] == "人民币千元"


def test_extract_midea_2023_financing_cash_flow_label() -> None:
    figures = extract_cash_flow_figures(
        page_number=163,
        page_text=MIDEA_2023_DUAL_CASH_FLOW_TEXT,
    )

    assert figures is not None
    assert figures["current_operating_cash_flow"] == 57_902_611
    assert figures["previous_operating_cash_flow"] == 34_657_828
    assert figures["current_investing_cash_flow"] == -31_219_855
    assert figures["current_financing_cash_flow"] == -17_910_213
    assert figures["current_exchange_effect"] == -17_251
    assert figures["current_net_cash_change"] == 8_755_292
    assert figures["current_opening_cash"] == 51_131_968
    assert figures["current_ending_cash"] == 59_887_260
    assert figures["previous_ending_cash"] == 51_131_968
    assert figures["unit"] == "人民币千元"
    assert figures["page_number"] == 163
