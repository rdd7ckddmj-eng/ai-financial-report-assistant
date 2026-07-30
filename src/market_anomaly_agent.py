"""Deterministic synthesis for the market-anomaly research Agent.

This module does not fetch data and does not predict prices.  It combines
already-calculated market evidence into a concise, auditable research status
that the interface can present consistently.
"""

from __future__ import annotations

from typing import Literal, TypedDict

from src.china_stock import MarketActivityEvidence, MarketActivityEvent


SignalStatus = Literal["triggered", "not_triggered", "unavailable"]
ReportStatus = Literal[
    "compound_anomaly",
    "single_anomaly",
    "no_strong_anomaly",
    "insufficient_data",
]


class AnomalySignal(TypedDict):
    """One independently evaluated, human-readable market signal."""

    name: str
    status: SignalStatus
    evidence: str
    limitation: str


class MarketAnomalyReport(TypedDict):
    """Auditable synthesis of latest-session market-activity evidence."""

    as_of_date: str
    status: ReportStatus
    headline: str
    conclusion: str
    triggered_signal_count: int
    available_signal_count: int
    recent_event_count: int
    signals: list[AnomalySignal]
    next_step: str
    limitation: str


def _format_percent(value: float | None) -> str:
    """Format optional ratios without presenting missing data as zero."""
    return "数据不足" if value is None else f"{value:.1%}"


def _build_price_signal(
    activity: MarketActivityEvidence,
) -> AnomalySignal:
    daily_return = activity["daily_return"]
    if daily_return is None:
        return {
            "name": "价格规则",
            "status": "unavailable",
            "evidence": "最新交易日缺少可核验的涨跌幅。",
            "limitation": activity["limit_up_note"],
        }

    is_triggered = activity["limit_up_status"] == "涨停候选"
    return {
        "name": "涨停候选",
        "status": "triggered" if is_triggered else "not_triggered",
        "evidence": (
            f"最新日涨跌幅为 {daily_return:.1%}，"
            f"板块规则参考阈值为 {activity['limit_up_reference']:.0%}；"
            f"系统判定为“{activity['limit_up_status']}”。"
        ),
        "limitation": activity["limit_up_note"],
    }


def _build_volume_signal(
    activity: MarketActivityEvidence,
) -> AnomalySignal:
    ratio = activity["volume_ratio_20d"]
    percentile = activity["volume_percentile_250d"]
    if ratio is None:
        return {
            "name": "成交量异动",
            "status": "unavailable",
            "evidence": "此前有效交易日不足，暂时不能建立20日成交量基准。",
            "limitation": "成交量基准必须排除当前交易日和未来交易日。",
        }

    is_triggered = ratio >= 2
    return {
        "name": "成交量异动",
        "status": "triggered" if is_triggered else "not_triggered",
        "evidence": (
            f"成交量为此前20日中位数的 {ratio:.2f} 倍，"
            f"历史分位为 {_format_percent(percentile)}；"
            f"系统分类为“{activity['volume_signal']}”。"
        ),
        "limitation": (
            "成交量放大只描述交易活跃度，不能单独解释价格变化原因。"
        ),
    }


def _build_turnover_signal(
    activity: MarketActivityEvidence,
) -> AnomalySignal:
    turnover = activity["turnover"]
    percentile = activity["turnover_percentile_250d"]
    if turnover is None or percentile is None:
        return {
            "name": "普通换手率高位",
            "status": "unavailable",
            "evidence": (
                f"普通换手率为 {_format_percent(turnover)}，"
                f"历史分位为 {_format_percent(percentile)}。"
            ),
            "limitation": (
                "当前公开数据不足以完成普通换手率历史位置判断；"
                "有效换手率仍需要可核验的时点自由流通股本。"
            ),
        }

    is_triggered = percentile >= 0.90
    return {
        "name": "普通换手率高位",
        "status": "triggered" if is_triggered else "not_triggered",
        "evidence": (
            f"普通换手率为 {turnover:.1%}，"
            f"位于此前最多250个交易日的 {percentile:.1%} 分位。"
        ),
        "limitation": (
            "这是普通换手率的历史相对位置，不等同于有效换手率，"
            "也不代表未来涨跌。"
        ),
    }


def build_market_anomaly_report(
    activity: MarketActivityEvidence,
    events: list[MarketActivityEvent],
) -> MarketAnomalyReport:
    """Combine three deterministic checks into one non-predictive report."""
    signals = [
        _build_price_signal(activity),
        _build_volume_signal(activity),
        _build_turnover_signal(activity),
    ]
    triggered = sum(
        signal["status"] == "triggered" for signal in signals
    )
    available = sum(
        signal["status"] != "unavailable" for signal in signals
    )

    if available == 0:
        status: ReportStatus = "insufficient_data"
        headline = "最新交易日证据不足"
        conclusion = (
            "三项异动检查均缺少足够证据，系统不生成市场异动判断。"
        )
    elif triggered >= 2:
        status = "compound_anomaly"
        headline = "最新交易日出现复合异动候选"
        conclusion = (
            f"三项独立检查中有 {triggered} 项触发。"
            "这说明多个交易活跃度指标同时处于规则阈值，"
            "适合继续核对当时已经公开的官方公告。"
        )
    elif triggered == 1:
        status = "single_anomaly"
        triggered_name = next(
            signal["name"]
            for signal in signals
            if signal["status"] == "triggered"
        )
        headline = f"最新交易日触发：{triggered_name}"
        conclusion = (
            "当前只有一项规则触发，属于单一异动线索，"
            "不能脱离价格、成交量、公告和公司基本面单独解释。"
        )
    else:
        status = "no_strong_anomaly"
        headline = "最新交易日未发现强异动"
        conclusion = (
            "现有可用指标均未触发强异动门槛。"
            "这只描述最新交易日，不代表未来不会发生变化。"
        )

    if events:
        next_step = (
            f"最近扫描到 {len(events)} 个候选日期；"
            "请选择其中一天，核对当日指标与此前已经公开的官方公告。"
        )
    else:
        next_step = (
            "最近扫描范围内没有候选日期；"
            "可继续查看K线或在 Historical Lens 中选择其他日期。"
        )

    return {
        "as_of_date": activity["latest_date"],
        "status": status,
        "headline": headline,
        "conclusion": conclusion,
        "triggered_signal_count": triggered,
        "available_signal_count": available,
        "recent_event_count": len(events),
        "signals": signals,
        "next_step": next_step,
        "limitation": (
            "本 Agent 只做可追溯的异常筛选和证据整理，"
            "不预测股价、不判断公告与异动的因果关系，也不构成投资建议。"
        ),
    }
