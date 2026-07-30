"""Deterministic historical analogs for market-anomaly research."""

from __future__ import annotations

import math
from datetime import date
from typing import TypedDict

from src.china_stock import MarketActivityEvent


class AnomalyAnalog(TypedDict):
    """One earlier anomaly ranked by transparent similarity rules."""

    date: str
    event_type: str
    close: float
    daily_return: float | None
    volume_ratio_20d: float | None
    turnover: float | None
    turnover_percentile_250d: float | None
    similarity_score: float
    comparable_dimension_count: int
    shared_signals: list[str]
    comparison_summary: str


_SIGNAL_WEIGHT = 0.40
_NUMERIC_WEIGHT = 0.20


def _event_signals(event: MarketActivityEvent) -> set[str]:
    """Return the three auditable screening signals for one event."""
    signals: set[str] = set()
    if event["limit_up_candidate"]:
        signals.add("涨停候选")
    volume_ratio = event["volume_ratio_20d"]
    if volume_ratio is not None and volume_ratio >= 2:
        signals.add("明显放量")
    if event["turnover_high_candidate"]:
        signals.add("普通换手率高位")
    return signals


def _linear_closeness(
    first: float | None,
    second: float | None,
    *,
    scale: float,
) -> float | None:
    """Score two finite values from one to zero over a fixed distance."""
    if first is None or second is None:
        return None
    if not math.isfinite(first) or not math.isfinite(second):
        return None
    return max(0.0, 1.0 - abs(first - second) / scale)


def _volume_closeness(
    first: float | None,
    second: float | None,
) -> float | None:
    """Compare positive volume multiples on a symmetric log scale."""
    if first is None or second is None:
        return None
    if (
        not math.isfinite(first)
        or not math.isfinite(second)
        or first <= 0
        or second <= 0
    ):
        return None
    log_distance = abs(math.log2(first / second))
    return max(0.0, 1.0 - log_distance / 2.0)


def _score_candidate(
    selected: MarketActivityEvent,
    candidate: MarketActivityEvent,
) -> tuple[float, int, list[str]] | None:
    """Return a renormalised score without converting missing data to zero."""
    selected_signals = _event_signals(selected)
    candidate_signals = _event_signals(candidate)
    signal_union = selected_signals | candidate_signals
    if not signal_union:
        return None

    shared_signals = sorted(selected_signals & candidate_signals)
    components: list[tuple[float, float]] = [
        (
            len(shared_signals) / len(signal_union),
            _SIGNAL_WEIGHT,
        )
    ]
    numeric_scores = (
        _linear_closeness(
            selected["daily_return"],
            candidate["daily_return"],
            scale=0.10,
        ),
        _volume_closeness(
            selected["volume_ratio_20d"],
            candidate["volume_ratio_20d"],
        ),
        _linear_closeness(
            selected["turnover_percentile_250d"],
            candidate["turnover_percentile_250d"],
            scale=1.0,
        ),
    )
    for score in numeric_scores:
        if score is not None:
            components.append((score, _NUMERIC_WEIGHT))

    if len(components) < 2:
        return None
    total_weight = sum(weight for _, weight in components)
    score = sum(
        value * weight for value, weight in components
    ) / total_weight
    return score, len(components), shared_signals


def find_historical_anomaly_analogs(
    selected: MarketActivityEvent,
    events: list[MarketActivityEvent],
    *,
    max_results: int = 3,
    min_similarity: float = 0.25,
) -> list[AnomalyAnalog]:
    """Rank strictly earlier anomaly candidates using transparent rules.

    This function compares event features only.  It does not use later returns
    and must not be interpreted as a forecast or trading recommendation.
    """
    if max_results < 1:
        raise ValueError("最多展示数量必须大于零。")
    if not 0 <= min_similarity <= 1:
        raise ValueError("最低相似度必须在0到1之间。")

    selected_date = date.fromisoformat(selected["date"])
    analogs: list[AnomalyAnalog] = []
    for candidate in events:
        try:
            candidate_date = date.fromisoformat(candidate["date"])
        except ValueError:
            continue
        if candidate_date >= selected_date:
            continue

        result = _score_candidate(selected, candidate)
        if result is None:
            continue
        score, dimension_count, shared_signals = result
        if score < min_similarity:
            continue
        if shared_signals:
            signal_text = "、".join(shared_signals)
            summary = f"共同触发：{signal_text}。"
        else:
            summary = "信号组合不同，数值形态仍可比较。"
        analogs.append(
            {
                "date": candidate["date"],
                "event_type": candidate["event_type"],
                "close": candidate["close"],
                "daily_return": candidate["daily_return"],
                "volume_ratio_20d": candidate["volume_ratio_20d"],
                "turnover": candidate["turnover"],
                "turnover_percentile_250d": (
                    candidate["turnover_percentile_250d"]
                ),
                "similarity_score": score,
                "comparable_dimension_count": dimension_count,
                "shared_signals": shared_signals,
                "comparison_summary": summary,
            }
        )

    analogs.sort(
        key=lambda item: (
            item["similarity_score"],
            date.fromisoformat(item["date"]),
        ),
        reverse=True,
    )
    return analogs[:max_results]
