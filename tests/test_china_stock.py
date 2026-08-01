import sys
from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

import src.china_stock as china_stock
from src.china_stock import (
    DataSourceError,
    add_moving_averages,
    build_company_identity,
    build_cninfo_pdf_url,
    calculate_market_activity,
    calculate_market_metrics,
    classify_announcement,
    fetch_announcements,
    fetch_market_history,
    infer_exchange,
    is_allowed_disclosure_url,
    merge_turnover_history,
    prepare_announcements,
    prepare_market_history,
    prepare_sina_turnover_history,
    prepare_tencent_market_history,
    reference_price_limit_ratio,
    resolve_company,
    scan_market_activity_events,
    select_latest_annual_report,
)


def _cninfo_row(
    announcement_id: int,
    published_at: str,
    *,
    title: str = "贵州茅台2025年年度报告",
) -> dict[str, object]:
    timestamp = int(pd.Timestamp(published_at, tz="UTC").timestamp() * 1000)
    return {
        "secCode": "600519",
        "secName": "贵州茅台",
        "announcementTitle": title,
        "announcementTime": timestamp,
        "announcementId": announcement_id,
        "orgId": "gssh0600519",
    }


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
    frame.loc[:19, "换手率"] = 1.0
    frame.loc[20, "换手率"] = 3.2
    company = build_company_identity("600519", "贵州茅台")

    activity = calculate_market_activity(frame, company)

    assert activity["volume_ratio_20d"] == pytest.approx(2.5)
    assert activity["volume_signal"] == "明显放量"
    assert activity["volume_percentile_250d"] == pytest.approx(1.0)
    assert activity["volume_percentile_sessions"] == 20
    assert activity["turnover"] == pytest.approx(0.032)
    assert activity["turnover_percentile_250d"] == pytest.approx(1.0)
    assert activity["turnover_percentile_sessions"] == 20
    assert activity["effective_turnover"] is None


def test_market_activity_percentile_uses_midrank_for_ties() -> None:
    frame = _market_rows(21)
    frame.loc[:, "成交量"] = 1_000_000
    frame.loc[:, "换手率"] = 2.0
    company = build_company_identity("600519", "贵州茅台")

    activity = calculate_market_activity(frame, company)

    assert activity["volume_percentile_250d"] == pytest.approx(0.5)
    assert activity["turnover_percentile_250d"] == pytest.approx(0.5)


def test_market_activity_percentile_requires_twenty_prior_sessions() -> None:
    frame = _market_rows(20)
    frame.loc[:, "换手率"] = 2.0
    company = build_company_identity("600519", "贵州茅台")

    activity = calculate_market_activity(frame, company)

    assert activity["volume_percentile_250d"] is None
    assert activity["volume_percentile_sessions"] == 19
    assert activity["turnover_percentile_250d"] is None
    assert activity["turnover_percentile_sessions"] == 19


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
    frame.loc[:39, "换手率"] = 1.0
    frame.loc[40, "换手率"] = 3.2
    company = build_company_identity("600519", "贵州茅台")

    events = scan_market_activity_events(frame, company)

    assert events[0]["date"] == frame.loc[40, "日期"].date().isoformat()
    assert events[0]["event_type"] == "明显放量 + 普通换手率高位"
    assert events[0]["volume_ratio_20d"] == pytest.approx(2.5)
    assert events[0]["volume_percentile_250d"] == pytest.approx(1.0)
    assert events[0]["turnover"] == pytest.approx(0.032)
    assert events[0]["turnover_percentile_250d"] == pytest.approx(1.0)
    assert events[0]["turnover_high_candidate"] is True


def test_activity_scanner_includes_high_ordinary_turnover_day() -> None:
    frame = _market_rows(45)
    frame.loc[:, "成交量"] = 1_000_000
    frame.loc[:, "换手率"] = 1.0
    frame.loc[40, "换手率"] = 4.0
    company = build_company_identity("600519", "贵州茅台")

    events = scan_market_activity_events(frame, company)
    target_date = frame.loc[40, "日期"].date().isoformat()
    event = next(item for item in events if item["date"] == target_date)

    assert event["event_type"] == "普通换手率高位"
    assert event["turnover_high_candidate"] is True
    assert event["turnover_percentile_250d"] == pytest.approx(1.0)


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
    assert event["volume_percentile_250d"] == pytest.approx(0.5)
    assert event["turnover_percentile_250d"] is None


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


def test_sina_turnover_uses_volume_divided_by_circulating_shares() -> None:
    frame = pd.DataFrame(
        {
            "date": ["2026-07-27"],
            "volume": [4_740_000],
            "outstanding_share": [1_000_000_000],
            "turnover": [0.99],
        }
    )

    prepared = prepare_sina_turnover_history(frame)

    assert prepared.loc[0, "turnover"] == pytest.approx(0.474)
    assert "成交量÷流通股本" in prepared.attrs["turnover_source"]


def test_turnover_merge_only_fills_missing_market_values() -> None:
    market = _market_rows(2)
    market["换手率"] = [1.5, float("nan")]
    market.attrs["source"] = "腾讯财经公开日线（备用源）"
    supplement = pd.DataFrame(
        {
            "date": market["日期"],
            "volume": [10_000_000, 20_000_000],
            "outstanding_share": [1_000_000_000, 1_000_000_000],
        }
    )

    merged = merge_turnover_history(market, supplement)

    assert merged.loc[0, "turnover"] == pytest.approx(1.5)
    assert merged.loc[1, "turnover"] == pytest.approx(2.0)
    assert merged.attrs["source"] == "腾讯财经公开日线（备用源）"
    assert merged.attrs["turnover_rows_filled"] == 1


def test_market_activity_reports_supplemental_turnover_source() -> None:
    frame = _market_rows(21)
    frame["换手率"] = 2.0
    frame.attrs["turnover_source"] = (
        "新浪财经流通股本计算（成交量÷流通股本）"
    )
    company = build_company_identity("600519", "贵州茅台")

    activity = calculate_market_activity(frame, company)

    assert "新浪财经" in activity["turnover_status"]
    assert activity["turnover"] == pytest.approx(0.02)


def test_fast_market_history_uses_bounded_provider_turnover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dates = pd.date_range("2026-06-01", periods=25, freq="B")
    eastmoney_calls = []
    tencent_calls = []

    def fail_eastmoney(**_: object) -> pd.DataFrame:
        eastmoney_calls.append(True)
        raise RuntimeError("primary source unavailable")

    def tencent_history(**kwargs: object) -> pd.DataFrame:
        tencent_calls.append(kwargs)
        return pd.DataFrame(
            {
                "date": dates,
                "open": 100.0,
                "close": 101.0,
                "high": 102.0,
                "low": 99.0,
                "volume": 2_000_000,
                "amount": 200_000_000,
                "turnover": 0.2,
            }
        )

    fake_akshare = SimpleNamespace(
        stock_zh_a_hist=fail_eastmoney,
        stock_zh_a_hist_tx=tencent_history,
    )
    monkeypatch.setitem(sys.modules, "akshare", fake_akshare)

    prepared = fetch_market_history(
        code="600519",
        start_date=dates[0].date(),
        end_date=dates[-1].date(),
    )
    activity = calculate_market_activity(
        prepared,
        build_company_identity("600519", "贵州茅台"),
    )

    assert prepared.attrs["source"] == "腾讯财经公开日线（快速源）"
    assert eastmoney_calls == []
    assert tencent_calls[0]["timeout"] == 6.0
    assert prepared["turnover"].notna().all()
    assert activity["turnover"] == pytest.approx(0.002)
    assert "腾讯财经" in activity["turnover_status"]


def test_market_history_uses_eastmoney_when_fast_source_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dates = pd.date_range("2026-06-01", periods=25, freq="B")

    def fail_tencent(**_: object) -> pd.DataFrame:
        raise RuntimeError("fast source unavailable")

    eastmoney_calls = []

    def eastmoney_history(**kwargs: object) -> pd.DataFrame:
        eastmoney_calls.append(kwargs)
        return _market_rows(len(dates))

    fake_akshare = SimpleNamespace(
        stock_zh_a_hist_tx=fail_tencent,
        stock_zh_a_hist=eastmoney_history,
    )
    monkeypatch.setitem(sys.modules, "akshare", fake_akshare)

    prepared = fetch_market_history(
        code="600519",
        start_date=dates[0].date(),
        end_date=dates[-1].date(),
    )

    assert prepared.attrs["source"] == "东方财富公开日线（备用源）"
    assert prepared.attrs["turnover_source"] == (
        "东方财富公开日线直接字段"
    )
    assert eastmoney_calls[0]["timeout"] == 6.0


def test_fast_market_history_supplements_missing_turnover_from_eastmoney(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dates = pd.date_range("2026-06-01", periods=25, freq="B")
    eastmoney_calls = []

    def tencent_history(**_: object) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "date": dates,
                "open": 100.0,
                "close": 101.0,
                "high": 102.0,
                "low": 99.0,
                "amount": 2_000_000,
            }
        )

    def eastmoney_history(**kwargs: object) -> pd.DataFrame:
        eastmoney_calls.append(kwargs)
        frame = _market_rows(len(dates))
        frame["日期"] = dates
        frame["换手率"] = 1.8
        return frame

    fake_akshare = SimpleNamespace(
        stock_zh_a_hist_tx=tencent_history,
        stock_zh_a_hist=eastmoney_history,
    )
    monkeypatch.setitem(sys.modules, "akshare", fake_akshare)

    prepared = fetch_market_history(
        code="600519",
        start_date=dates[0].date(),
        end_date=dates[-1].date(),
    )

    assert prepared.attrs["source"] == "腾讯财经公开日线（快速源）"
    assert prepared.attrs["turnover_source"] == (
        "东方财富公开日线直接字段（与腾讯价格按日期合并）"
    )
    assert prepared.attrs["turnover_rows_filled"] == len(dates)
    assert prepared["turnover"].eq(1.8).all()
    assert eastmoney_calls[0]["start_date"] == "20260601"
    assert eastmoney_calls[0]["end_date"] == dates[-1].strftime("%Y%m%d")
    assert eastmoney_calls[0]["timeout"] == 6.0


def test_turnover_supplement_failure_keeps_valid_fast_price_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dates = pd.date_range("2026-06-01", periods=25, freq="B")

    def tencent_history(**_: object) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "date": dates,
                "open": 100.0,
                "close": 101.0,
                "high": 102.0,
                "low": 99.0,
                "amount": 2_000_000,
            }
        )

    def fail_eastmoney(**_: object) -> pd.DataFrame:
        raise RuntimeError("turnover supplement unavailable")

    fake_akshare = SimpleNamespace(
        stock_zh_a_hist_tx=tencent_history,
        stock_zh_a_hist=fail_eastmoney,
    )
    monkeypatch.setitem(sys.modules, "akshare", fake_akshare)

    prepared = fetch_market_history(
        code="600519",
        start_date=dates[0].date(),
        end_date=dates[-1].date(),
    )

    assert len(prepared) == len(dates)
    assert prepared.attrs["source"] == "腾讯财经公开日线（快速源）"
    assert prepared.attrs["turnover_source"] == "暂未取得"
    assert prepared["turnover"].isna().all()


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


def test_fetch_announcements_uses_bounded_parallel_cninfo_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_pages: list[int] = []
    observed_categories: list[str] = []
    monkeypatch.setattr(
        china_stock,
        "_load_cninfo_stock_ids",
        lambda: {"600519": "gssh0600519"},
    )

    def fake_page(
        payload: dict[str, str],
        page_number: int,
    ) -> dict[str, object]:
        requested_pages.append(page_number)
        observed_categories.append(payload["category"])
        return {
            "totalAnnouncement": 61,
            "announcements": [
                _cninfo_row(
                    page_number,
                    f"2026-04-{page_number:02d} 08:00:00",
                    title=f"贵州茅台第{page_number}页年度报告",
                )
            ],
        }

    monkeypatch.setattr(
        china_stock,
        "_fetch_cninfo_announcement_page",
        fake_page,
    )

    result = fetch_announcements(
        "600519",
        date(2025, 1, 1),
        date(2026, 7, 31),
        category="年报",
    )

    assert sorted(requested_pages) == [1, 2, 3]
    assert set(observed_categories) == {"category_ndbg_szsh"}
    assert list(result["title"]) == [
        "贵州茅台第3页年度报告",
        "贵州茅台第2页年度报告",
        "贵州茅台第1页年度报告",
    ]
    assert result.attrs["retrieved_pages"] == 3
    assert result.attrs["total_announcements"] == 61
    assert all(
        str(url).startswith(
            "https://www.cninfo.com.cn/new/disclosure/detail?"
        )
        for url in result["url"]
    )


def test_fetch_announcements_rejects_oversized_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        china_stock,
        "_load_cninfo_stock_ids",
        lambda: {"600519": "gssh0600519"},
    )
    monkeypatch.setattr(
        china_stock,
        "_fetch_cninfo_announcement_page",
        lambda payload, page_number: {
            "totalAnnouncement": (
                china_stock.CNINFO_PAGE_SIZE
                * (china_stock.CNINFO_MAX_PAGES + 1)
            ),
            "announcements": [],
        },
    )

    with pytest.raises(DataSourceError, match="安全读取上限"):
        fetch_announcements(
            "600519",
            date(2025, 1, 1),
            date(2026, 7, 31),
        )


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


def test_select_latest_annual_report_prefers_same_year_chinese_original() -> None:
    frame = pd.DataFrame(
        {
            "代码": ["600519", "600519", "600519"],
            "简称": ["贵州茅台"] * 3,
            "公告标题": [
                "贵州茅台2025年年度报告（英文版）",
                "贵州茅台2025年年度报告",
                "贵州茅台2024年年度报告",
            ],
            "公告时间": ["2026-04-17", "2026-04-03", "2025-04-03"],
            "公告链接": [
                "https://static.cninfo.com.cn/2025-en.pdf",
                "https://static.cninfo.com.cn/2025-zh.pdf",
                "https://static.cninfo.com.cn/2024-zh.pdf",
            ],
        }
    )

    latest = select_latest_annual_report(prepare_announcements(frame))

    assert latest is not None
    assert latest["title"] == "贵州茅台2025年年度报告"


def test_select_latest_annual_report_uses_english_when_only_option() -> None:
    frame = pd.DataFrame(
        {
            "代码": ["600519", "600519"],
            "简称": ["贵州茅台", "贵州茅台"],
            "公告标题": [
                "贵州茅台2025年年度报告（英文版）",
                "贵州茅台2024年年度报告",
            ],
            "公告时间": ["2026-04-17", "2025-04-03"],
            "公告链接": [
                "https://static.cninfo.com.cn/2025-en.pdf",
                "https://static.cninfo.com.cn/2024-zh.pdf",
            ],
        }
    )

    latest = select_latest_annual_report(prepare_announcements(frame))

    assert latest is not None
    assert latest["title"] == "贵州茅台2025年年度报告（英文版）"
