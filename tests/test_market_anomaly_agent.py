from src.china_stock import MarketActivityEvidence, MarketActivityEvent
from src.market_anomaly_agent import build_market_anomaly_report


def _activity(
    *,
    daily_return: float | None = 0.02,
    volume_ratio: float | None = 1.1,
    turnover: float | None = 0.025,
    turnover_percentile: float | None = 0.60,
    limit_status: str = "未触及参考阈值",
) -> MarketActivityEvidence:
    return {
        "latest_date": "2026-07-29",
        "daily_return": daily_return,
        "volume_ratio_20d": volume_ratio,
        "volume_signal": "接近前20日常态",
        "volume_percentile_250d": 0.60,
        "volume_percentile_sessions": 250,
        "turnover": turnover,
        "turnover_status": "公开日线已提供普通换手率",
        "turnover_percentile_250d": turnover_percentile,
        "turnover_percentile_sessions": 250,
        "effective_turnover": None,
        "effective_turnover_status": "缺少可核验的时点自由流通股本，暂不计算",
        "limit_up_reference": 0.10,
        "limit_up_status": limit_status,
        "limit_up_note": "仍需交易所数据复核。",
    }


def _event() -> MarketActivityEvent:
    return {
        "date": "2026-07-28",
        "event_type": "明显放量",
        "close": 100.0,
        "daily_return": 0.03,
        "daily_return_basis": "公开行情源涨跌幅",
        "volume_ratio_20d": 2.5,
        "volume_percentile_250d": 0.99,
        "turnover": 0.04,
        "turnover_percentile_250d": 0.88,
        "turnover_high_candidate": False,
        "limit_up_reference": 0.10,
        "limit_up_candidate": False,
    }


def test_agent_reports_compound_anomaly_from_independent_signals() -> None:
    activity = _activity(
        daily_return=0.10,
        volume_ratio=2.5,
        turnover=0.06,
        turnover_percentile=0.95,
        limit_status="涨停候选",
    )
    activity["volume_signal"] = "明显放量"

    report = build_market_anomaly_report(activity, [_event()])

    assert report["status"] == "compound_anomaly"
    assert report["triggered_signal_count"] == 3
    assert report["available_signal_count"] == 3
    assert report["recent_event_count"] == 1
    assert "复合异动候选" in report["headline"]
    assert "不预测股价" in report["limitation"]


def test_agent_does_not_turn_normal_activity_into_a_signal() -> None:
    report = build_market_anomaly_report(_activity(), [])

    assert report["status"] == "no_strong_anomaly"
    assert report["triggered_signal_count"] == 0
    assert all(
        signal["status"] == "not_triggered"
        for signal in report["signals"]
    )


def test_agent_marks_missing_inputs_instead_of_using_zero() -> None:
    activity = _activity(
        daily_return=None,
        volume_ratio=None,
        turnover=None,
        turnover_percentile=None,
        limit_status="数据不足",
    )
    activity["volume_percentile_250d"] = None

    report = build_market_anomaly_report(activity, [])

    assert report["status"] == "insufficient_data"
    assert report["available_signal_count"] == 0
    assert all(
        signal["status"] == "unavailable"
        for signal in report["signals"]
    )
    assert all(
        "0.0%" not in signal["evidence"]
        for signal in report["signals"]
    )
