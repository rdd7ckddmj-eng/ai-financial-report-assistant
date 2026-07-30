import pytest

from src.anomaly_analogs import find_historical_anomaly_analogs
from src.china_stock import MarketActivityEvent


def _event(
    event_date: str,
    *,
    event_type: str = "明显放量",
    daily_return: float | None = 0.05,
    volume_ratio: float | None = 2.5,
    turnover_percentile: float | None = 0.95,
    limit_up: bool = False,
    turnover_high: bool = False,
) -> MarketActivityEvent:
    return {
        "date": event_date,
        "event_type": event_type,
        "close": 100.0,
        "daily_return": daily_return,
        "daily_return_basis": "公开行情源涨跌幅",
        "volume_ratio_20d": volume_ratio,
        "volume_percentile_250d": 0.95,
        "turnover": 0.03,
        "turnover_percentile_250d": turnover_percentile,
        "turnover_high_candidate": turnover_high,
        "limit_up_reference": 0.10,
        "limit_up_candidate": limit_up,
    }


def test_analogs_exclude_selected_and_later_dates() -> None:
    selected = _event("2026-06-10")
    events = [
        selected,
        _event("2026-06-11"),
        _event("2026-05-20"),
    ]

    analogs = find_historical_anomaly_analogs(selected, events)

    assert [item["date"] for item in analogs] == ["2026-05-20"]


def test_analogs_rank_closer_features_first() -> None:
    selected = _event(
        "2026-06-10",
        daily_return=0.08,
        volume_ratio=3.0,
        turnover_percentile=0.94,
        turnover_high=True,
        event_type="明显放量 + 普通换手率高位",
    )
    closer = _event(
        "2026-04-01",
        daily_return=0.075,
        volume_ratio=2.8,
        turnover_percentile=0.91,
        turnover_high=True,
        event_type="明显放量 + 普通换手率高位",
    )
    farther = _event(
        "2026-05-01",
        daily_return=0.02,
        volume_ratio=2.0,
        turnover_percentile=0.30,
        event_type="明显放量",
    )

    analogs = find_historical_anomaly_analogs(
        selected,
        [farther, closer],
    )

    assert [item["date"] for item in analogs] == [
        "2026-04-01",
        "2026-05-01",
    ]
    assert analogs[0]["similarity_score"] > analogs[1]["similarity_score"]
    assert analogs[0]["shared_signals"] == [
        "明显放量",
        "普通换手率高位",
    ]


def test_analogs_renormalise_missing_dimensions() -> None:
    selected = _event(
        "2026-06-10",
        daily_return=0.05,
        volume_ratio=None,
        turnover_percentile=None,
        limit_up=True,
        event_type="涨停候选",
    )
    candidate = _event(
        "2026-05-01",
        daily_return=0.05,
        volume_ratio=None,
        turnover_percentile=None,
        limit_up=True,
        event_type="涨停候选",
    )

    analogs = find_historical_anomaly_analogs(selected, [candidate])

    assert analogs[0]["comparable_dimension_count"] == 2
    assert analogs[0]["similarity_score"] == pytest.approx(1.0)


def test_analogs_require_one_numeric_comparison() -> None:
    selected = _event(
        "2026-06-10",
        daily_return=None,
        volume_ratio=None,
        turnover_percentile=None,
    )
    candidate = _event(
        "2026-05-01",
        daily_return=None,
        volume_ratio=None,
        turnover_percentile=None,
    )

    assert find_historical_anomaly_analogs(selected, [candidate]) == []


def test_analogs_use_newer_date_as_deterministic_tiebreaker() -> None:
    selected = _event("2026-06-10")
    older = _event("2026-04-01")
    newer = _event("2026-05-01")

    analogs = find_historical_anomaly_analogs(
        selected,
        [older, newer],
    )

    assert [item["date"] for item in analogs] == [
        "2026-05-01",
        "2026-04-01",
    ]


def test_analogs_validate_max_results() -> None:
    with pytest.raises(ValueError, match="最多展示数量"):
        find_historical_anomaly_analogs(
            _event("2026-06-10"),
            [],
            max_results=0,
        )


def test_analogs_reject_very_weak_matches() -> None:
    selected = _event(
        "2026-06-10",
        daily_return=0.10,
        volume_ratio=4.0,
        turnover_percentile=1.0,
        turnover_high=True,
        event_type="明显放量 + 普通换手率高位",
    )
    weak_candidate = _event(
        "2026-05-01",
        daily_return=-0.10,
        volume_ratio=0.5,
        turnover_percentile=0.0,
        limit_up=True,
        event_type="涨停候选",
    )

    assert find_historical_anomaly_analogs(
        selected,
        [weak_candidate],
    ) == []


def test_analogs_validate_similarity_threshold() -> None:
    with pytest.raises(ValueError, match="最低相似度"):
        find_historical_anomaly_analogs(
            _event("2026-06-10"),
            [],
            min_similarity=1.1,
        )
