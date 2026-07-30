import pandas as pd
import pytest

from src.china_stock import (
    add_moving_averages,
    build_company_identity,
    build_cninfo_pdf_url,
    calculate_market_activity,
    calculate_market_metrics,
    classify_announcement,
    infer_exchange,
    is_allowed_disclosure_url,
    prepare_announcements,
    prepare_market_history,
    prepare_tencent_market_history,
    reference_price_limit_ratio,
    resolve_company,
    scan_market_activity_events,
    select_latest_annual_report,
)


def _market_rows(count: int = 300) -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=count, freq="B")
    close = pd.Series([100 + index * 0.2 for index in range(count)])
    return pd.DataFrame(
        {
            "日期": dates,
            "开盘": close - 0.2,
            "最高": close + 0.6,
            "最低": close - 0.8,
            "收盘": close,
            "成交量": 1_000_000,
            "成交额": 100_000_000,
        }
    )


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("600519", "SH"),
        ("000001", "SZ"),
        ("300750", "SZ"),
        ("688981", "SH"),
        ("920001", "BJ"),
    ],
)
def test_infer_exchange(code: str, expected: str) -> None:
    assert infer_exchange(code) == expected


def test_resolve_company_by_code_and_name() -> None:
    directory = pd.DataFrame(
        {
            "code": ["600519", "300750"],
            "name": ["贵州茅台", "宁德时代"],
        }
    )

    by_code = resolve_company("600519.SH", directory)
    by_name = resolve_company("宁德时代", directory)

    assert by_code[0]["canonical_code"] == "600519.SH"
    assert by_code[0]["name"] == "贵州茅台"
    assert by_name[0]["code"] == "300750"


def test_prepare_market_history_and_metrics() -> None:
    prepared = prepare_market_history(_market_rows())
    metrics = calculate_market_metrics(prepared)
    with_averages = add_moving_averages(prepared)

    assert len(prepared) == 300
    assert metrics["latest_close"] == pytest.approx(159.8)
    assert metrics["return_20d"] is not None
    assert metrics["return_60d"] is not None
    assert metrics["return_250d"] is not None
    assert metrics["max_drawdown"] == pytest.approx(0.0)
    assert with_averages["ma_60"].notna().sum() == 241


def test_market_activity_uses_previous_20_day_median_volume() -> None:
    frame = _market_rows(21)
    frame.loc[:19, "成交量"] = 1_000_000
    frame.loc[20, "成交量"] = 2_500_000
    frame.loc[20, "换手率"] = 3.2
    company = build_company_identity("600519", "贵州茅台")

    activity = calculate_market_activity(frame, company)

    assert activity["volume_ratio_20d"] == pytest.approx(2.5)
    assert activity["volume_signal"] == "明显放量"
    assert activity["turnover"] == pytest.approx(0.032)
    assert activity["effective_turnover"] is None


def test_market_activity_marks_limit_up_only_as_candidate() -> None:
    frame = _market_rows(21)
    frame.loc[20, "收盘"] = frame.loc[19, "收盘"] * 1.10
    frame.loc[20, "最高"] = frame.loc[20, "收盘"]
    company = build_company_identity("600519", "贵州茅台")

    activity = calculate_market_activity(frame, company)

    assert activity["limit_up_reference"] == pytest.approx(0.10)
    assert activity["limit_up_status"] == "涨停候选"
    assert "仍需交易所数据复核" in activity["limit_up_note"]


def test_activity_scanner_excludes_event_day_from_volume_baseline() -> None:
    frame = _market_rows(45)
    frame.loc[:, "成交量"] = 1_000_000
    frame.loc[40, "成交量"] = 2_500_000
    frame.loc[40, "换手率"] = 3.2
    company = build_company_identity("600519", "贵州茅台")

    events = scan_market_activity_events(frame, company)

    assert events[0]["date"] == frame.loc[40, "日期"].date().isoformat()
    assert events[0]["event_type"] == "明显放量"
    assert events[0]["volume_ratio_20d"] == pytest.approx(2.5)
    assert events[0]["turnover"] == pytest.approx(0.032)


def test_activity_scanner_marks_board_rule_limit_candidate() -> None:
    frame = _market_rows(30)
    frame.loc[25, "收盘"] = frame.loc[24, "收盘"] * 1.20
    frame.loc[25, "最高"] = frame.loc[25, "收盘"]
    company = build_company_identity("300750", "宁德时代")

    events = scan_market_activity_events(frame, company)
    target_date = frame.loc[25, "日期"].date().isoformat()
    event = next(item for item in events if item["date"] == target_date)

    assert event["limit_up_reference"] == pytest.approx(0.20)
    assert event["limit_up_candidate"] is True
    assert "涨停候选" in event["event_type"]


def test_activity_scanner_prefers_provider_daily_change() -> None:
    frame = _market_rows(30)
    frame["涨跌幅"] = float("nan")
    frame.loc[25, "涨跌幅"] = 10.0
    company = build_company_identity("600519", "贵州茅台")

    events = scan_market_activity_events(frame, company)
    target_date = frame.loc[25, "日期"].date().isoformat()
    event = next(item for item in events if item["date"] == target_date)

    assert event["daily_return"] == pytest.approx(0.10)
    assert event["daily_return_basis"] == "公开行情源涨跌幅"
    assert event["limit_up_candidate"] is True


def test_activity_scanner_returns_newest_candidates_first() -> None:
    frame = _market_rows(50)
    frame.loc[:, "成交量"] = 1_000_000
    frame.loc[25, "成交量"] = 2_100_000
    frame.loc[45, "成交量"] = 3_000_000
    company = build_company_identity("600519", "贵州茅台")

    events = scan_market_activity_events(
        frame,
        company,
        max_results=1,
    )

    assert [item["date"] for item in events] == [
        frame.loc[45, "日期"].date().isoformat()
    ]


@pytest.mark.parametrize(
    ("code", "name", "market_date", "expected"),
    [
        ("600519", "贵州茅台", "2026-07-29", 0.10),
        ("688981", "中芯国际", "2026-07-29", 0.20),
        ("300750", "宁德时代", "2026-07-29", 0.20),
        ("920001", "测试北交所公司", "2026-07-29", 0.30),
        ("000001", "ST测试", "2026-07-29", 0.05),
        ("600001", "*ST测试", "2026-07-05", 0.05),
        ("600001", "*ST测试", "2026-07-06", 0.10),
    ],
)
def test_reference_price_limit_ratio(
    code: str,
    name: str,
    market_date: str,
    expected: float,
) -> None:
    company = build_company_identity(code, name)

    ratio = reference_price_limit_ratio(
        company,
        pd.Timestamp(market_date).date(),
    )

    assert ratio == pytest.approx(expected)


def test_invalid_ohlc_rows_are_removed() -> None:
    frame = _market_rows(2)
    frame.loc[1, "最高"] = 1

    prepared = prepare_market_history(frame)

    assert len(prepared) == 1


def test_tencent_daily_schema_maps_amount_to_volume() -> None:
    frame = pd.DataFrame(
        {
            "date": ["2026-07-27"],
            "open": [10.0],
            "close": [10.2],
            "high": [10.3],
            "low": [9.9],
            "amount": [1_234_567],
        }
    )

    prepared = prepare_tencent_market_history(frame)

    assert prepared.loc[0, "volume"] == 1_234_567
    assert pd.isna(prepared.loc[0, "amount"])


def test_announcement_classification_uses_attention_not_sentiment() -> None:
    assert classify_announcement("2025年年度报告") == ("财务报告", "高")
    assert classify_announcement("关于股份回购进展的公告") == (
        "分红与回购",
        "中",
    )
    assert classify_announcement("股票可能被终止上市的风险提示") == (
        "监管与风险",
        "高",
    )


def test_announcement_links_are_limited_to_disclosure_sources() -> None:
    assert is_allowed_disclosure_url(
        "https://static.cninfo.com.cn/finalpage/report.pdf"
    )
    assert not is_allowed_disclosure_url("https://example.com/report.pdf")


def test_cninfo_detail_link_builds_bounded_official_download_url() -> None:
    detail_url = (
        "http://www.cninfo.com.cn/new/disclosure/detail?"
        "plate=szse&stockCode=000001&announcementId=1212345678"
        "&announcementTime=2025-03-15%2018:00"
    )

    assert build_cninfo_pdf_url(detail_url) == (
        "https://static.cninfo.com.cn/finalpage/"
        "2025-03-15/1212345678.PDF"
    )


def test_cninfo_pdf_builder_rejects_untrusted_or_incomplete_links() -> None:
    with pytest.raises(ValueError):
        build_cninfo_pdf_url(
            "https://example.com/new/disclosure/detail?"
            "announcementId=1212345678&announcementTime=2025-03-15"
        )
    with pytest.raises(ValueError):
        build_cninfo_pdf_url(
            "https://www.cninfo.com.cn/new/disclosure/detail?"
            "announcementId=1212345678"
        )


def test_select_latest_annual_report_excludes_summary() -> None:
    frame = pd.DataFrame(
        {
            "代码": ["600519", "600519", "600519"],
            "简称": ["贵州茅台"] * 3,
            "公告标题": [
                "贵州茅台2025年年度报告摘要",
                "贵州茅台2025年年度报告",
                "贵州茅台2024年年度报告",
            ],
            "公告时间": ["2026-04-01", "2026-04-01", "2025-04-01"],
            "公告链接": [
                "https://static.cninfo.com.cn/a.pdf",
                "https://static.cninfo.com.cn/b.pdf",
                "https://static.cninfo.com.cn/c.pdf",
            ],
        }
    )

    prepared = prepare_announcements(frame)
    latest = select_latest_annual_report(prepared)

    assert latest is not None
    assert latest["title"] == "贵州茅台2025年年度报告"


def test_select_latest_annual_report_excludes_half_year_report() -> None:
    frame = pd.DataFrame(
        {
            "代码": ["600519", "600519"],
            "简称": ["贵州茅台", "贵州茅台"],
            "公告标题": [
                "贵州茅台2024年半年度报告",
                "贵州茅台2023年年度报告",
            ],
            "公告时间": ["2024-08-09", "2024-04-03"],
            "公告链接": [
                "https://static.cninfo.com.cn/half-year.pdf",
                "https://static.cninfo.com.cn/annual.pdf",
            ],
        }
    )

    latest = select_latest_annual_report(prepare_announcements(frame))

    assert latest is not None
    assert latest["title"] == "贵州茅台2023年年度报告"
