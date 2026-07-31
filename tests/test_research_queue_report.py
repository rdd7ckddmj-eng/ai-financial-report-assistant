from datetime import date

from src.china_stock import MarketActivityEvidence, build_company_identity
from src.market_radar import (
    ResearchQueueRow,
    build_market_radar_row,
    build_research_queue_row,
)
from src.research_queue_report import build_research_queue_report_html


def _queue_row() -> ResearchQueueRow:
    activity: MarketActivityEvidence = {
        "latest_date": "2026-07-31",
        "daily_return": 0.031,
        "volume_ratio_20d": 2.5,
        "volume_signal": "明显放量",
        "volume_percentile_250d": 0.99,
        "volume_percentile_sessions": 250,
        "turnover": 0.041,
        "turnover_status": "普通换手率历史高位",
        "turnover_percentile_250d": 0.936,
        "turnover_percentile_sessions": 250,
        "effective_turnover": None,
        "effective_turnover_status": "数据不足",
        "limit_up_reference": 0.10,
        "limit_up_status": "未触及参考阈值",
        "limit_up_note": "测试",
    }
    radar_row = build_market_radar_row(
        build_company_identity("600519", "贵州茅台"),
        activity,
        market_source="腾讯财经公开日线（备用源）",
        turnover_source="新浪财经流通股本计算",
    )
    return build_research_queue_row(
        radar_row,
        [
            {
                "title": "贵州茅台2025年年度报告",
                "date": date(2026, 7, 30),
                "url": "https://static.cninfo.com.cn/report.pdf",
                "category": "财务报告",
                "attention": "高",
            }
        ],
        as_of_date=date(2026, 7, 31),
        disclosure_status="已核验近45日公告 1 条",
    )


def test_queue_report_preserves_priorities_sources_and_official_links() -> None:
    result = build_research_queue_report_html(
        [_queue_row()],
        scan_date=date(2026, 7, 31),
    )

    assert "<!doctype html>" in result
    assert "自选股研究任务简报" in result
    assert "贵州茅台" in result
    assert "600519.SH" in result
    assert "P1｜立即核查" in result
    assert "3.1%" in result
    assert "2.50 倍" in result
    assert "93.6%" in result
    assert "市场端同时触发2项异动证据" in result
    assert "贵州茅台2025年年度报告" in result
    assert "https://static.cninfo.com.cn/report.pdf" in result
    assert "腾讯财经公开日线（备用源）" in result
    assert "普通换手率不等于有效换手率" in result
    assert "不构成买入、卖出或持有建议" in result


def test_queue_report_records_failures_without_inventing_replacements() -> None:
    result = build_research_queue_report_html(
        [_queue_row()],
        scan_date=date(2026, 7, 31),
        failures=["300750：当前无法取得公开行情"],
    )

    assert "未完成扫描" in result
    assert "300750：当前无法取得公开行情" in result
    assert "没有用旧样例或 AI 猜测替代" in result


def test_queue_report_escapes_text_and_rejects_unsafe_disclosure_url() -> None:
    row = _queue_row()
    row["company"]["name"] = "<script>alert('x')</script>"
    assert row["latest_disclosure"] is not None
    row["latest_disclosure"]["source_url"] = "javascript:alert(1)"

    result = build_research_queue_report_html(
        [row],
        scan_date=date(2026, 7, 31),
    )

    assert "<script>alert" not in result
    assert "&lt;script&gt;" in result
    assert "javascript:alert(1)" not in result
    assert "原文链接未通过官方域名校验" in result
