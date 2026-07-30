from src.china_stock import (
    MarketActivityEvidence,
    build_company_identity,
)
from src.market_radar import (
    build_market_radar_row,
    parse_watchlist_codes,
    rank_market_radar,
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
