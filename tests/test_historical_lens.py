from datetime import date, timedelta

import pandas as pd
import pytest

from src.historical_lens import (
    EvidenceRecord,
    calculate_historical_snapshot,
    calculate_later_outcomes,
    filter_evidence_as_of,
    slice_market_as_of,
)


def _market_rows(count: int = 300) -> pd.DataFrame:
    dates = pd.date_range("2024-01-02", periods=count, freq="B")
    close = pd.Series([100 + index for index in range(count)])
    return pd.DataFrame(
        {
            "date": dates,
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": [1_000_000 + index for index in range(count)],
            "amount": 100_000_000,
            "turnover": 2.5,
        }
    )


def _evidence(
    source_id: str,
    title: str,
    published_date: str,
    period_end: str | None = None,
) -> EvidenceRecord:
    return {
        "source_id": source_id,
        "source_type": "official_disclosure",
        "title": title,
        "published_date": published_date,
        "period_end": period_end,
        "source_url": f"https://static.cninfo.com.cn/{source_id}.pdf",
        "page_number": None,
        "evidence_grade": "A",
        "verification_status": "verified",
    }


def test_filter_evidence_excludes_future_publications() -> None:
    records = [
        _evidence("known", "截止日前公告", "2025-03-31"),
        _evidence("future", "截止日后公告", "2025-04-02"),
    ]

    result = filter_evidence_as_of(records, date(2025, 4, 1))

    assert [item["source_id"] for item in result["accepted"]] == ["known"]
    assert [item["source_id"] for item in result["excluded"]] == ["future"]
    assert result["excluded"][0]["reason"] == "发布日期晚于历史截止日"
    assert result["input_count"] == 2
    assert result["accepted_count"] == 1


def test_period_end_does_not_override_late_publication_date() -> None:
    annual_report = _evidence(
        "annual-report",
        "2024年年度报告",
        "2025-03-28",
        period_end="2024-12-31",
    )

    result = filter_evidence_as_of([annual_report], "2024-12-31")

    assert result["accepted"] == []
    assert result["excluded_count"] == 1


def test_market_slice_never_contains_future_rows() -> None:
    frame = _market_rows(10)
    cutoff = frame.loc[4, "date"].date()

    sliced = slice_market_as_of(frame, cutoff)

    assert len(sliced) == 5
    assert sliced["date"].max() == cutoff


def test_historical_snapshot_uses_effective_trading_date_and_bounded_window() -> None:
    frame = _market_rows(300)
    requested_date = frame.loc[280, "date"].date()

    snapshot = calculate_historical_snapshot(
        frame,
        requested_date,
        source="测试行情",
    )

    assert snapshot["requested_date"] == requested_date.isoformat()
    assert snapshot["effective_market_date"] == requested_date.isoformat()
    assert snapshot["latest_close"] == pytest.approx(380.0)
    assert snapshot["turnover"] == pytest.approx(0.025)
    assert snapshot["observations"] == 251
    assert snapshot["return_250d"] is not None
    assert snapshot["source"] == "测试行情"


def test_historical_snapshot_uses_previous_session_on_weekend() -> None:
    frame = _market_rows(10)
    friday = frame.loc[3, "date"].date()
    saturday = friday + timedelta(days=1)

    snapshot = calculate_historical_snapshot(
        frame,
        saturday,
        source="测试行情",
    )

    assert snapshot["requested_date"] == saturday.isoformat()
    assert snapshot["effective_market_date"] == friday.isoformat()


def test_later_outcomes_are_separate_and_use_trading_day_horizons() -> None:
    frame = _market_rows(300)
    cutoff = frame.loc[100, "date"].date()

    outcomes = calculate_later_outcomes(frame, cutoff)

    assert [item["horizon_trading_days"] for item in outcomes] == [
        20,
        60,
        120,
    ]
    assert all(item["status"] == "available" for item in outcomes)
    assert outcomes[0]["outcome_close"] == pytest.approx(220.0)
    assert outcomes[0]["return_since_base"] == pytest.approx(0.10)
    assert outcomes[0]["maximum_drawdown"] == pytest.approx(0.0)


def test_later_outcomes_report_insufficient_future_data() -> None:
    frame = _market_rows(30)
    cutoff = frame.loc[20, "date"].date()

    outcomes = calculate_later_outcomes(frame, cutoff)

    assert all(
        item["status"] == "insufficient_future_data"
        for item in outcomes
    )
    assert all(item["return_since_base"] is None for item in outcomes)


def test_snapshot_rejects_dates_before_available_market_history() -> None:
    with pytest.raises(
        ValueError,
        match="历史截止日之前没有有效行情数据",
    ):
        calculate_historical_snapshot(
            _market_rows(10),
            "2020-01-01",
            source="测试行情",
        )
