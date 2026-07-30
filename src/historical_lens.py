"""Point-in-time evidence and market calculations for Historical Lens.

The functions in this module deliberately keep information available at the
historical cut-off separate from outcomes that happened later.  This makes the
time boundary testable and prevents an LLM or page renderer from accidentally
using future information in a historical snapshot.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, Literal, TypedDict

import pandas as pd

from src.china_stock import calculate_market_metrics, prepare_market_history


class EvidenceRecord(TypedDict):
    """One dated source that may or may not be known at the cut-off."""

    source_id: str
    source_type: str
    title: str
    published_date: date | str
    period_end: date | str | None
    source_url: str
    page_number: int | None
    evidence_grade: str
    verification_status: str


class ExcludedEvidence(TypedDict):
    """Evidence excluded from a historical snapshot with an explicit reason."""

    source_id: str
    title: str
    published_date: str
    reason: str


class EvidenceFilterResult(TypedDict):
    """Accepted evidence plus an auditable record of exclusions."""

    as_of_date: str
    accepted: list[EvidenceRecord]
    excluded: list[ExcludedEvidence]
    input_count: int
    accepted_count: int
    excluded_count: int


class HistoricalMarketSnapshot(TypedDict):
    """Market state calculated only from observations available at the cut-off."""

    requested_date: str
    effective_market_date: str
    latest_close: float
    volume: float
    turnover: float | None
    return_20d: float | None
    return_60d: float | None
    return_250d: float | None
    annualised_volatility: float | None
    max_drawdown: float
    observations: int
    source: str
    adjustment: str


OutcomeStatus = Literal["available", "insufficient_future_data"]


class OutcomeWindow(TypedDict):
    """A later market outcome kept separate from the historical snapshot."""

    label: str
    horizon_trading_days: int
    status: OutcomeStatus
    base_date: str
    base_close: float
    outcome_date: str | None
    outcome_close: float | None
    return_since_base: float | None
    maximum_gain: float | None
    maximum_drawdown: float | None


def _as_date(value: date | datetime | str, field_name: str) -> date:
    """Convert supported date values without silently accepting bad inputs."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError as error:
        raise ValueError(f"{field_name} 不是有效的 ISO 日期。") from error


def filter_evidence_as_of(
    records: Iterable[EvidenceRecord],
    as_of_date: date | str,
) -> EvidenceFilterResult:
    """Keep only evidence published on or before the historical cut-off."""
    cutoff = _as_date(as_of_date, "历史截止日")
    accepted: list[EvidenceRecord] = []
    excluded: list[ExcludedEvidence] = []

    for record in records:
        published = _as_date(record["published_date"], "证据发布日期")
        if published <= cutoff:
            accepted.append(record)
            continue
        excluded.append(
            {
                "source_id": record["source_id"],
                "title": record["title"],
                "published_date": published.isoformat(),
                "reason": "发布日期晚于历史截止日",
            }
        )

    return {
        "as_of_date": cutoff.isoformat(),
        "accepted": accepted,
        "excluded": excluded,
        "input_count": len(accepted) + len(excluded),
        "accepted_count": len(accepted),
        "excluded_count": len(excluded),
    }


def slice_market_as_of(
    frame: pd.DataFrame,
    as_of_date: date | str,
) -> pd.DataFrame:
    """Return validated market rows no later than the requested date."""
    cutoff = _as_date(as_of_date, "历史截止日")
    prepared = prepare_market_history(frame)
    return prepared.loc[prepared["date"] <= cutoff].reset_index(drop=True)


def calculate_historical_snapshot(
    frame: pd.DataFrame,
    as_of_date: date | str,
    *,
    source: str,
    adjustment: str = "不复权",
) -> HistoricalMarketSnapshot:
    """Calculate a standard trailing-250-session point-in-time market state."""
    cutoff = _as_date(as_of_date, "历史截止日")
    available = slice_market_as_of(frame, cutoff)
    if available.empty:
        raise ValueError("历史截止日之前没有有效行情数据。")

    # 251 closes are required to calculate a 250-session point-to-point
    # return.  The same bounded window keeps volatility and drawdown comparable
    # between different historical dates.
    calculation_window = available.tail(251).reset_index(drop=True)
    metrics = calculate_market_metrics(calculation_window)
    latest_row = calculation_window.iloc[-1]
    turnover_value = latest_row["turnover"]
    turnover = (
        None if pd.isna(turnover_value) else float(turnover_value) / 100
    )

    return {
        "requested_date": cutoff.isoformat(),
        "effective_market_date": metrics["latest_date"],
        "latest_close": metrics["latest_close"],
        "volume": float(latest_row["volume"]),
        "turnover": turnover,
        "return_20d": metrics["return_20d"],
        "return_60d": metrics["return_60d"],
        "return_250d": metrics["return_250d"],
        "annualised_volatility": metrics["annualised_volatility"],
        "max_drawdown": metrics["max_drawdown"],
        "observations": metrics["observations"],
        "source": source,
        "adjustment": adjustment,
    }


def calculate_later_outcomes(
    frame: pd.DataFrame,
    as_of_date: date | str,
    *,
    horizons: tuple[tuple[str, int], ...] = (
        ("约1个月", 20),
        ("约3个月", 60),
        ("约6个月", 120),
    ),
) -> list[OutcomeWindow]:
    """Calculate later outcomes without feeding them into the snapshot."""
    cutoff = _as_date(as_of_date, "历史截止日")
    prepared = prepare_market_history(frame)
    base_candidates = prepared.index[prepared["date"] <= cutoff]
    if len(base_candidates) == 0:
        raise ValueError("历史截止日之前没有有效行情数据。")

    base_position = int(base_candidates[-1])
    base_row = prepared.iloc[base_position]
    base_close = float(base_row["close"])
    base_date = base_row["date"].isoformat()
    outcomes: list[OutcomeWindow] = []

    for label, trading_days in horizons:
        outcome_position = base_position + trading_days
        if outcome_position >= len(prepared):
            outcomes.append(
                {
                    "label": label,
                    "horizon_trading_days": trading_days,
                    "status": "insufficient_future_data",
                    "base_date": base_date,
                    "base_close": base_close,
                    "outcome_date": None,
                    "outcome_close": None,
                    "return_since_base": None,
                    "maximum_gain": None,
                    "maximum_drawdown": None,
                }
            )
            continue

        window = prepared.iloc[
            base_position : outcome_position + 1
        ].copy()
        close = window["close"].astype(float)
        outcome_row = window.iloc[-1]
        outcomes.append(
            {
                "label": label,
                "horizon_trading_days": trading_days,
                "status": "available",
                "base_date": base_date,
                "base_close": base_close,
                "outcome_date": outcome_row["date"].isoformat(),
                "outcome_close": float(outcome_row["close"]),
                "return_since_base": float(close.iloc[-1] / base_close - 1),
                "maximum_gain": float(close.max() / base_close - 1),
                "maximum_drawdown": float(
                    (close / close.cummax() - 1).min()
                ),
            }
        )
    return outcomes
