import pandas as pd
import pytest

from src.china_stock import (
    add_moving_averages,
    build_cninfo_pdf_url,
    calculate_market_metrics,
    classify_announcement,
    infer_exchange,
    is_allowed_disclosure_url,
    prepare_announcements,
    prepare_market_history,
    prepare_tencent_market_history,
    resolve_company,
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
