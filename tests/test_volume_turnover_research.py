import pandas as pd
import pytest

from src.china_stock import build_company_identity
from src.volume_turnover_research import (
    build_volume_turnover_history,
    build_volume_turnover_snapshot,
    calculate_effective_turnover,
)


def _market_frame(count: int = 60) -> pd.DataFrame:
    dates = pd.date_range("2026-01-05", periods=count, freq="B")
    close = pd.Series([100 + index * 0.1 for index in range(count)])
    frame = pd.DataFrame(
        {
            "date": dates,
            "open": close - 0.2,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": 1_000_000.0,
            "amount": 100_000_000.0,
            "turnover": 1.0,
        }
    )
    frame.attrs["source"] = "测试公开行情"
    frame.attrs["turnover_source"] = "测试普通换手率"
    return frame


def test_volume_turnover_snapshot_builds_point_in_time_review() -> None:
    frame = _market_frame()
    frame.loc[55, "volume"] = 2_500_000
    frame.loc[55, "turnover"] = 4.0
    frame.loc[59, "volume"] = 1_500_000
    frame.loc[59, "turnover"] = 3.0
    company = build_company_identity("600519", "贵州茅台")

    snapshot = build_volume_turnover_snapshot(frame, company)

    assert snapshot["latest_volume"] == pytest.approx(1_500_000)
    assert snapshot["previous_20_median_volume"] == pytest.approx(1_000_000)
    assert snapshot["volume_ratio_20d"] == pytest.approx(1.5)
    assert snapshot["ordinary_turnover"] == pytest.approx(0.03)
    assert snapshot["price_volume_pattern"] == "放量上涨"
    assert snapshot["high_volume_days"] == 1
    assert snapshot["high_turnover_days"] >= 1
    assert snapshot["compound_activity_days"] == 1
    assert snapshot["source"] == "测试公开行情"
    assert len(snapshot["observations"]) == 4


def test_volume_turnover_snapshot_preserves_missing_turnover() -> None:
    frame = _market_frame(21)
    frame["turnover"] = float("nan")
    company = build_company_identity("600519", "贵州茅台")

    snapshot = build_volume_turnover_snapshot(frame, company)

    assert snapshot["ordinary_turnover"] is None
    assert snapshot["turnover_percentile_250d"] is None
    assert snapshot["high_turnover_days"] == 0
    assert "未提供" in snapshot["observations"][2]


def test_volume_turnover_history_excludes_current_day_from_baseline() -> None:
    frame = _market_frame(21)
    frame.loc[20, "volume"] = 3_000_000

    history = build_volume_turnover_history(frame)

    assert history.loc[20, "previous_20_median_volume"] == pytest.approx(
        1_000_000
    )
    assert history.loc[20, "volume_ratio_20d"] == pytest.approx(3.0)
    assert history.loc[20, "ordinary_turnover"] == pytest.approx(0.01)


def test_volume_turnover_history_is_bounded() -> None:
    history = build_volume_turnover_history(
        _market_frame(100),
        lookback_sessions=60,
    )

    assert len(history) == 60
    assert history.iloc[0]["date"] == (
        _market_frame(100).iloc[40]["date"].date()
    )


def test_effective_turnover_uses_verified_free_float_ratio() -> None:
    result = calculate_effective_turnover(
        ordinary_turnover=0.04,
        circulating_shares=100_000,
        free_float_shares=80_000,
    )

    assert result["free_float_ratio"] == pytest.approx(0.8)
    assert result["adjustment_multiple"] == pytest.approx(1.25)
    assert result["effective_turnover"] == pytest.approx(0.05)
    assert "自由流通股本" in result["formula"]


@pytest.mark.parametrize(
    ("circulating_shares", "free_float_shares", "message"),
    [
        (0, 10, "必须大于零"),
        (100, 0, "必须大于零"),
        (100, 101, "不能大于"),
    ],
)
def test_effective_turnover_rejects_invalid_denominators(
    circulating_shares: float,
    free_float_shares: float,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        calculate_effective_turnover(
            ordinary_turnover=0.04,
            circulating_shares=circulating_shares,
            free_float_shares=free_float_shares,
        )
