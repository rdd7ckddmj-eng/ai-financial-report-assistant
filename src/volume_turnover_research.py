"""Deterministic volume and turnover research for one A-share company.

The module reuses validated daily market history.  It describes participation
and historical position without turning activity into a price forecast.
Effective turnover is calculated only when the user supplies a verified
free-float denominator.
"""

from __future__ import annotations

import math
from typing import TypedDict

import pandas as pd

from src.china_stock import (
    CompanyIdentity,
    MarketActivityEvent,
    calculate_market_activity,
    prepare_market_history,
    scan_market_activity_events,
)


class VolumeTurnoverSnapshot(TypedDict):
    """One compact, deterministic participation review."""

    latest_date: str
    latest_volume: float
    previous_20_median_volume: float | None
    volume_ratio_20d: float | None
    volume_percentile_250d: float | None
    volume_percentile_sessions: int
    ordinary_turnover: float | None
    turnover_status: str
    turnover_percentile_250d: float | None
    turnover_percentile_sessions: int
    price_volume_pattern: str
    recent_window_sessions: int
    high_volume_days: int
    high_turnover_days: int
    compound_activity_days: int
    events: list[MarketActivityEvent]
    observations: list[str]
    source: str


class EffectiveTurnoverVerification(TypedDict):
    """A user-verified free-float adjustment of ordinary turnover."""

    ordinary_turnover: float
    circulating_shares: float
    free_float_shares: float
    free_float_ratio: float
    adjustment_multiple: float
    effective_turnover: float
    formula: str


def _price_volume_pattern(
    daily_return: float | None,
    volume_ratio: float | None,
) -> str:
    """Classify the latest price-volume combination without predicting it."""
    if volume_ratio is None:
        return "量能数据不足"
    if daily_return is None:
        return "明显放量" if volume_ratio >= 2 else "量能接近常态"

    if volume_ratio >= 1.3 and daily_return > 0:
        return "放量上涨"
    if volume_ratio >= 1.3 and daily_return < 0:
        return "放量下跌"
    if volume_ratio <= 0.7 and daily_return > 0:
        return "缩量上涨"
    if volume_ratio <= 0.7 and daily_return < 0:
        return "缩量下跌"
    return "量能接近常态"


def build_volume_turnover_history(
    frame: pd.DataFrame,
    *,
    lookback_sessions: int = 60,
) -> pd.DataFrame:
    """Build a bounded chart series using only information known each day."""
    if lookback_sessions < 1:
        raise ValueError("图表交易日数量必须大于零。")

    prepared = prepare_market_history(frame)
    if prepared.empty:
        raise ValueError("没有有效行情数据用于成交量与换手率研究。")

    volume = prepared["volume"].astype(float)
    previous_20_median = volume.shift(1).rolling(
        window=20,
        min_periods=20,
    ).median()
    volume_ratio = volume / previous_20_median.where(
        previous_20_median > 0
    )
    daily_return = prepared["pct_change"].astype(float) / 100
    calculated_return = prepared["close"].astype(float).pct_change()
    daily_return = daily_return.where(daily_return.notna(), calculated_return)
    ordinary_turnover = (
        pd.to_numeric(prepared["turnover"], errors="coerce") / 100
    )

    history = pd.DataFrame(
        {
            "date": prepared["date"],
            "daily_return": daily_return,
            "volume": volume,
            "previous_20_median_volume": previous_20_median,
            "volume_ratio_20d": volume_ratio,
            "ordinary_turnover": ordinary_turnover,
        }
    ).tail(lookback_sessions)
    history.attrs["source"] = prepared.attrs.get(
        "source",
        "公开行情适配器",
    )
    history.attrs["turnover_source"] = prepared.attrs.get(
        "turnover_source",
        "",
    )
    return history.reset_index(drop=True)


def build_volume_turnover_snapshot(
    frame: pd.DataFrame,
    company: CompanyIdentity,
    *,
    recent_window_sessions: int = 20,
) -> VolumeTurnoverSnapshot:
    """Summarise recent participation without an LLM or future data."""
    if recent_window_sessions < 1:
        raise ValueError("复盘交易日数量必须大于零。")

    prepared = prepare_market_history(frame)
    if prepared.empty:
        raise ValueError("没有有效行情数据用于成交量与换手率研究。")

    activity = calculate_market_activity(prepared, company)
    events = scan_market_activity_events(
        prepared,
        company,
        lookback_sessions=recent_window_sessions,
        max_results=recent_window_sessions,
    )
    high_volume_days = sum(
        event["volume_ratio_20d"] is not None
        and event["volume_ratio_20d"] >= 2
        for event in events
    )
    high_turnover_days = sum(
        event["turnover_high_candidate"] for event in events
    )
    compound_activity_days = sum(
        event["volume_ratio_20d"] is not None
        and event["volume_ratio_20d"] >= 2
        and event["turnover_high_candidate"]
        for event in events
    )

    latest = prepared.iloc[-1]
    previous_20_median_volume: float | None = None
    if len(prepared) >= 21:
        baseline = float(
            prepared["volume"].iloc[-21:-1].astype(float).median()
        )
        if baseline > 0:
            previous_20_median_volume = baseline

    pattern = _price_volume_pattern(
        activity["daily_return"],
        activity["volume_ratio_20d"],
    )
    observations = [
        (
            "最新量能："
            + (
                "前20日样本不足，暂不计算成交量倍数。"
                if activity["volume_ratio_20d"] is None
                else (
                    f"成交量为前20日中位数的 "
                    f"{activity['volume_ratio_20d']:.2f} 倍，"
                    f"价格—量能组合为“{pattern}”。"
                )
            )
        ),
        (
            "成交量历史位置："
            + (
                "有效历史样本不足。"
                if activity["volume_percentile_250d"] is None
                else (
                    f"位于此前 {activity['volume_percentile_sessions']} "
                    "个有效交易日的 "
                    f"{activity['volume_percentile_250d']:.1%} 分位。"
                )
            )
        ),
        (
            "普通换手率："
            + (
                "当前公开数据未提供可用值。"
                if activity["turnover"] is None
                else (
                    f"最新为 {activity['turnover']:.2%}，历史分位"
                    + (
                        "样本不足。"
                        if activity["turnover_percentile_250d"] is None
                        else (
                            "为 "
                            f"{activity['turnover_percentile_250d']:.1%}。"
                        )
                    )
                )
            )
        ),
        (
            f"近 {min(recent_window_sessions, len(prepared))} 个交易日："
            f"明显放量 {high_volume_days} 日，普通换手率历史高位 "
            f"{high_turnover_days} 日，两项同时出现 "
            f"{compound_activity_days} 日。"
        ),
    ]

    return {
        "latest_date": activity["latest_date"],
        "latest_volume": float(latest["volume"]),
        "previous_20_median_volume": previous_20_median_volume,
        "volume_ratio_20d": activity["volume_ratio_20d"],
        "volume_percentile_250d": activity["volume_percentile_250d"],
        "volume_percentile_sessions": activity[
            "volume_percentile_sessions"
        ],
        "ordinary_turnover": activity["turnover"],
        "turnover_status": activity["turnover_status"],
        "turnover_percentile_250d": activity[
            "turnover_percentile_250d"
        ],
        "turnover_percentile_sessions": activity[
            "turnover_percentile_sessions"
        ],
        "price_volume_pattern": pattern,
        "recent_window_sessions": min(recent_window_sessions, len(prepared)),
        "high_volume_days": high_volume_days,
        "high_turnover_days": high_turnover_days,
        "compound_activity_days": compound_activity_days,
        "events": events,
        "observations": observations,
        "source": str(
            prepared.attrs.get("source", "公开行情适配器")
        ),
    }


def calculate_effective_turnover(
    ordinary_turnover: float,
    circulating_shares: float,
    free_float_shares: float,
) -> EffectiveTurnoverVerification:
    """Adjust ordinary turnover with a verified free-float denominator.

    Both share inputs must use the same unit and the same point-in-time date.
    The formula avoids assuming whether the provider's daily volume is in
    shares or lots:

    effective turnover
    = ordinary turnover × circulating shares ÷ free-float shares
    """
    values = {
        "普通换手率": ordinary_turnover,
        "无限售流通股本": circulating_shares,
        "自由流通股本": free_float_shares,
    }
    for label, value in values.items():
        if not math.isfinite(float(value)):
            raise ValueError(f"{label}必须是有限数值。")
    if ordinary_turnover < 0:
        raise ValueError("普通换手率不能为负数。")
    if circulating_shares <= 0 or free_float_shares <= 0:
        raise ValueError("两个股本数值都必须大于零。")
    if free_float_shares > circulating_shares:
        raise ValueError("自由流通股本不能大于无限售流通股本。")

    free_float_ratio = free_float_shares / circulating_shares
    adjustment_multiple = circulating_shares / free_float_shares
    effective_turnover = ordinary_turnover * adjustment_multiple
    return {
        "ordinary_turnover": float(ordinary_turnover),
        "circulating_shares": float(circulating_shares),
        "free_float_shares": float(free_float_shares),
        "free_float_ratio": float(free_float_ratio),
        "adjustment_multiple": float(adjustment_multiple),
        "effective_turnover": float(effective_turnover),
        "formula": (
            "普通换手率 × 无限售流通股本 ÷ 自由流通股本"
        ),
    }
