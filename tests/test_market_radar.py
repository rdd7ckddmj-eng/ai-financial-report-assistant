from datetime import date

from src.china_stock import (
    MarketActivityEvidence,
    build_company_identity,
)
from src.market_radar import (
    build_market_radar_row,
    build_research_queue_row,
    parse_watchlist_codes,
    rank_market_radar,
    rank_research_queue,
)


def _activity(
    *,
    daily_return: float | None = 0.01,
    volume_ratio: float | None = 1.1,
    turnover_percentile: float | None = 0.5,
    limit_up: bool = False,
) -> MarketActivityEvidence:
    return {
        "latest_date": "2026-07-30",
        "daily_return": daily_return,
        "volume_ratio_20d": volume_ratio,
        "volume_signal": "测试",
        "volume_percentile_250d": 0.5,
        "volume_percentile_sessions": 250,
        "turnover": 0.03,
        "turnover_status": "测试",
        "turnover_percentile_250d": turnover_percentile,
        "turnover_percentile_sessions": 250,
        "effective_turnover": None,
        "effective_turnover_status": "数据不足",
        "limit_up_reference": 0.10,
        "limit_up_status": "涨停候选" if limit_up else "未触及参考阈值",
        "limit_up_note": "测试",
    }


def _row(
    code: str,
    activity: MarketActivityEvidence,
):
    return build_market_radar_row(
        build_company_identity(code, f"公司{code}"),
        activity,
        market_source="测试行情",
        turnover_source="测试换手率",
    )


def test_parse_watchlist_codes_limits_and_explains_input() -> None:
    result = parse_watchlist_codes(
        "600519，300750 600519;bad;000001、002594;688981;601398"
    )

    assert result["codes"] == [
        "600519",
        "300750",
        "000001",
        "002594",
        "688981",
    ]
    assert result["invalid_tokens"] == ["bad"]
    assert result["duplicate_count"] == 1
    assert result["omitted_count"] == 1


def test_radar_builds_independent_trigger_evidence() -> None:
    row = _row(
        "600519",
        _activity(
            daily_return=0.101,
            volume_ratio=2.4,
            turnover_percentile=0.93,
            limit_up=True,
        ),
    )

    assert row["triggered_signals"] == [
        "涨停候选",
        "明显放量",
        "普通换手率历史高位",
    ]
    assert row["trigger_count"] == 3
    assert row["available_signal_count"] == 3
    assert row["radar_status"] == "复合异动"


def test_radar_keeps_missing_evidence_distinct_from_zero() -> None:
    row = _row(
        "600519",
        _activity(
            daily_return=0.01,
            volume_ratio=None,
            turnover_percentile=None,
        ),
    )

    assert row["trigger_count"] == 0
    assert row["available_signal_count"] == 1
    assert row["radar_status"] == "未触发（部分数据缺失）"


def test_radar_ranks_trigger_count_then_limit_candidate() -> None:
    compound = _row(
        "300750",
        _activity(volume_ratio=2.2, turnover_percentile=0.92),
    )
    limit_only = _row(
        "600519",
        _activity(limit_up=True),
    )
    volume_only = _row(
        "000001",
        _activity(volume_ratio=2.8),
    )

    ranked = rank_market_radar([volume_only, limit_only, compound])

    assert [row["company"]["code"] for row in ranked] == [
        "300750",
        "600519",
        "000001",
    ]


def test_recent_high_attention_disclosure_creates_p1_research_task() -> None:
    row = build_research_queue_row(
        _row("600519", _activity()),
        [
            {
                "title": "贵州茅台2025年年度报告",
                "date": date(2026, 7, 30),
                "url": (
                    "https://static.cninfo.com.cn/finalpage/"
                    "2026-07-30/1234567890.PDF"
                ),
                "category": "财务报告",
                "attention": "高",
            }
        ],
        as_of_date=date(2026, 7, 31),
    )

    assert row["research_priority"] == "P1｜立即核查"
    assert row["latest_disclosure"] is not None
    assert row["latest_disclosure"]["days_old"] == 1
    assert "高关注官方公告" in row["research_reasons"][0]


def test_research_queue_excludes_future_and_untrusted_disclosures() -> None:
    row = build_research_queue_row(
        _row("600519", _activity()),
        [
            {
                "title": "未来公告",
                "date": date(2026, 8, 1),
                "url": (
                    "https://static.cninfo.com.cn/finalpage/"
                    "2026-08-01/1234567891.PDF"
                ),
                "category": "其他公告",
                "attention": "高",
            },
            {
                "title": "非官方网页摘要",
                "date": date(2026, 7, 31),
                "url": "https://example.com/summary",
                "category": "其他公告",
                "attention": "高",
            },
        ],
        as_of_date=date(2026, 7, 31),
    )

    assert row["latest_disclosure"] is None
    assert row["research_priority"] == "P3｜常规跟踪"
    assert "没有可展示" in row["research_reasons"][0]


def test_recent_high_attention_evidence_is_not_hidden_by_newer_low_item() -> None:
    row = build_research_queue_row(
        _row("600519", _activity()),
        [
            {
                "title": "今日一般性公告",
                "date": date(2026, 7, 31),
                "url": "https://static.cninfo.com.cn/today.pdf",
                "category": "其他公告",
                "attention": "低",
            },
            {
                "title": "昨日高关注公告",
                "date": date(2026, 7, 30),
                "url": "https://static.cninfo.com.cn/yesterday.pdf",
                "category": "财务报告",
                "attention": "高",
            },
        ],
        as_of_date=date(2026, 7, 31),
    )

    assert row["latest_disclosure"] is not None
    assert row["latest_disclosure"]["title"] == "今日一般性公告"
    assert row["research_priority"] == "P1｜立即核查"
    assert any("财务报告" in reason for reason in row["research_reasons"])


def test_compound_market_evidence_stays_p1_when_disclosures_fail() -> None:
    row = build_research_queue_row(
        _row(
            "300750",
            _activity(volume_ratio=2.4, turnover_percentile=0.95),
        ),
        None,
        as_of_date=date(2026, 7, 31),
        disclosure_status="官方公告源暂不可用",
    )

    assert row["research_priority"] == "P1｜立即核查"
    assert row["latest_disclosure"] is None
    assert any("未用新闻或AI猜测替代" in reason for reason in row["research_reasons"])


def test_research_queue_ranks_priority_without_investment_score() -> None:
    p3 = build_research_queue_row(
        _row("000001", _activity()),
        [],
        as_of_date=date(2026, 7, 31),
    )
    p2 = build_research_queue_row(
        _row("600519", _activity(volume_ratio=2.2)),
        [],
        as_of_date=date(2026, 7, 31),
    )
    p1 = build_research_queue_row(
        _row(
            "300750",
            _activity(volume_ratio=2.2, turnover_percentile=0.92),
        ),
        [],
        as_of_date=date(2026, 7, 31),
    )

    ranked = rank_research_queue([p3, p2, p1])

    assert [row["research_priority"] for row in ranked] == [
        "P1｜立即核查",
        "P2｜优先复盘",
        "P3｜常规跟踪",
    ]
