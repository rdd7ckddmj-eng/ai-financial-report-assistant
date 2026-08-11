"""Rank the most important first-pass research question deterministically.

This module does not fetch data, call an LLM, score a company, or predict a
share price.  It only ranks review questions already supported by the current
research run, while keeping missing evidence explicit.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Literal, TypedDict

from src.china_stock import is_allowed_disclosure_url


ConclusionState = Literal["attention", "clear", "insufficient"]


class ConclusionPillar(TypedDict):
    """One plain-language status used in the first-pass conclusion card."""

    key: str
    label: str
    state: ConclusionState
    status_label: str
    summary: str
    basis: str


class ResearchConclusion(TypedDict):
    """One ranked research conclusion without an investment score."""

    headline: str
    explanation: str
    next_question: str
    evidence_summary: str
    primary_key: str
    pillars: list[ConclusionPillar]


class _ConclusionCandidate(TypedDict):
    key: str
    priority: int
    headline: str
    explanation: str
    next_question: str


STATE_LABELS: dict[ConclusionState, str] = {
    "attention": "需要关注",
    "clear": "未触发预设异常",
    "insufficient": "证据不足",
}


def _finite_number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _lane_by_key(
    evidence_lanes: Sequence[Mapping[str, object]],
) -> dict[str, Mapping[str, object]]:
    return {
        str(lane.get("key", "")): lane
        for lane in evidence_lanes
        if str(lane.get("key", ""))
    }


def _candidate(
    key: str,
    priority: int,
    headline: str,
    explanation: str,
    next_question: str,
) -> _ConclusionCandidate:
    return {
        "key": key,
        "priority": priority,
        "headline": headline,
        "explanation": explanation,
        "next_question": next_question,
    }


def _latest_financial_point(
    financial_history: Mapping[str, object] | None,
) -> Mapping[str, object] | None:
    if not isinstance(financial_history, Mapping):
        return None
    raw_points = financial_history.get("points")
    if not isinstance(raw_points, Sequence) or isinstance(
        raw_points, (str, bytes)
    ):
        return None
    points = [point for point in raw_points if isinstance(point, Mapping)]
    if not points:
        return None
    return max(
        points,
        key=lambda point: int(_finite_number(point.get("period_year")) or 0),
    )


def _snapshot_growth_rates(
    financial_snapshot: Mapping[str, object] | None,
) -> dict[str, float]:
    if not isinstance(financial_snapshot, Mapping):
        return {}
    raw_metrics = financial_snapshot.get("metrics")
    if not isinstance(raw_metrics, Sequence) or isinstance(
        raw_metrics, (str, bytes)
    ):
        return {}
    rates: dict[str, float] = {}
    for metric in raw_metrics:
        if not isinstance(metric, Mapping):
            continue
        key = str(metric.get("key", "")).strip()
        rate = _finite_number(metric.get("change_rate"))
        if key and rate is not None:
            rates[key] = rate
    return rates


def _financial_candidate_and_pillar(
    financial_lane: Mapping[str, object] | None,
    financial_history: Mapping[str, object] | None,
    financial_snapshot: Mapping[str, object] | None,
) -> tuple[_ConclusionCandidate | None, ConclusionPillar]:
    status = (
        str(financial_lane.get("status", "unavailable"))
        if financial_lane
        else "unavailable"
    )
    source = str(financial_lane.get("source", "")) if financial_lane else ""
    latest = _latest_financial_point(financial_history)
    if latest is not None:
        year = int(_finite_number(latest.get("period_year")) or 0)
        revenue_growth = _finite_number(latest.get("revenue_growth"))
        profit_growth = _finite_number(latest.get("net_profit_growth"))
        cash_flow_growth = _finite_number(
            latest.get("operating_cash_flow_growth")
        )
        if profit_growth is not None and cash_flow_growth is not None:
            if profit_growth > 0 and cash_flow_growth < 0:
                candidate = _candidate(
                    "financial_cash_mismatch",
                    95,
                    "利润增长但经营现金流下降，现金转化质量最值得先核验",
                    (
                        f"{year} 年归母净利润同比增长 {profit_growth:.1%}，"
                        f"经营现金流同比下降 {abs(cash_flow_growth):.1%}。"
                        "两者方向背离不等于财务有误，但需要回到年报核对"
                        "营运资本、应收款和一次性项目。"
                    ),
                    "利润增长为何没有同步转化为经营现金流？",
                )
                return candidate, {
                    "key": "financial",
                    "label": "财务状态",
                    "state": "attention",
                    "status_label": STATE_LABELS["attention"],
                    "summary": "利润与经营现金流增速方向背离",
                    "basis": f"{year} 年已核验多年财务数据",
                }
        if revenue_growth is not None and profit_growth is not None:
            if revenue_growth > 0 and profit_growth < 0:
                candidate = _candidate(
                    "financial_profit_pressure",
                    92,
                    "收入增长但利润下降，盈利质量与成本压力最值得先核验",
                    (
                        f"{year} 年营业收入同比增长 {revenue_growth:.1%}，"
                        f"归母净利润同比下降 {abs(profit_growth):.1%}。"
                        "需要进一步区分毛利率、费用、减值和非经常性项目影响。"
                    ),
                    "收入增长为何没有转化为利润增长？",
                )
                return candidate, {
                    "key": "financial",
                    "label": "财务状态",
                    "state": "attention",
                    "status_label": STATE_LABELS["attention"],
                    "summary": "收入与利润增速方向背离",
                    "basis": f"{year} 年已核验多年财务数据",
                }
        return None, {
            "key": "financial",
            "label": "财务状态",
            "state": "clear",
            "status_label": STATE_LABELS["clear"],
            "summary": "当前已核验数据未触发两项方向背离规则",
            "basis": f"{year} 年已核验多年财务数据",
        }

    snapshot_ready = (
        source == "最新完整年度报告自动提取候选"
        and isinstance(financial_snapshot, Mapping)
        and financial_snapshot.get("status") == "ready_for_human_review"
    )
    if snapshot_ready:
        rates = _snapshot_growth_rates(financial_snapshot)
        revenue_growth = rates.get("revenue")
        profit_growth = rates.get("net_profit")
        cash_flow_growth = rates.get("operating_cash_flow")
        if profit_growth is not None and cash_flow_growth is not None:
            if profit_growth > 0 and cash_flow_growth < 0:
                candidate = _candidate(
                    "snapshot_cash_mismatch",
                    88,
                    "单期候选显示利润增长、经营现金流下降，需优先核对年报原文",
                    (
                        "这是自动提取的单期方向背离候选，尚未经过人工"
                        "逐页复核，不能直接作为公司判断。"
                    ),
                    "年报原文中的净利润、经营现金流和对应页码是否提取正确？",
                )
                return candidate, {
                    "key": "financial",
                    "label": "财务状态",
                    "state": "attention",
                    "status_label": STATE_LABELS["attention"],
                    "summary": "单期候选出现利润与现金流方向背离",
                    "basis": "最新年报自动提取候选，等待人工复核",
                }
        if revenue_growth is not None and profit_growth is not None:
            if revenue_growth > 0 and profit_growth < 0:
                candidate = _candidate(
                    "snapshot_profit_pressure",
                    87,
                    "单期候选显示收入增长、利润下降，需优先核对年报原文",
                    (
                        "这是自动提取的单期方向背离候选，尚未经过人工"
                        "逐页复核，不能直接作为公司判断。"
                    ),
                    "年报原文中的收入、净利润和对应页码是否提取正确？",
                )
                return candidate, {
                    "key": "financial",
                    "label": "财务状态",
                    "state": "attention",
                    "status_label": STATE_LABELS["attention"],
                    "summary": "单期候选出现收入与利润方向背离",
                    "basis": "最新年报自动提取候选，等待人工复核",
                }
        return None, {
            "key": "financial",
            "label": "财务状态",
            "state": "insufficient",
            "status_label": STATE_LABELS["insufficient"],
            "summary": "已有单期候选，但不足以代表多年财务趋势",
            "basis": "最新年报自动提取候选，等待人工复核",
        }

    if status == "partial":
        summary = "财务证据仅覆盖单一年度或仍待复核"
    else:
        summary = "尚无可用于方向判断的公司财务证据"
    return None, {
        "key": "financial",
        "label": "财务状态",
        "state": "insufficient",
        "status_label": STATE_LABELS["insufficient"],
        "summary": summary,
        "basis": "缺失数据不会按零处理，也不会套用其他公司样例",
    }


def _market_candidates_and_pillar(
    market_lane: Mapping[str, object] | None,
    activity: Mapping[str, object] | None,
) -> tuple[list[_ConclusionCandidate], ConclusionPillar]:
    candidates: list[_ConclusionCandidate] = []
    status = (
        str(market_lane.get("status", "unavailable"))
        if market_lane
        else "unavailable"
    )
    signals: list[str] = []
    if isinstance(activity, Mapping):
        if activity.get("limit_up_status") == "涨停候选":
            signals.append("涨停候选")
            candidates.append(
                _candidate(
                    "market_limit_up",
                    90,
                    "最新交易日触及涨停候选，市场异动最值得先核验",
                    (
                        "涨停候选只由交易规则和行情计算得出；需要结合"
                        "当日及邻近日期官方公告判断事件背景。"
                    ),
                    "异动日期附近是否存在需要优先阅读的官方公告？",
                )
            )
        volume_ratio = _finite_number(activity.get("volume_ratio_20d"))
        if volume_ratio is not None and volume_ratio >= 2:
            signals.append("明显放量")
            candidates.append(
                _candidate(
                    "market_volume",
                    84,
                    "成交量明显放大，交易活跃度最值得先核验",
                    (
                        f"最新成交量为前20日中位数的 {volume_ratio:.2f} 倍，"
                        "属于预设放量候选。"
                    ),
                    "放量是否与公告、业绩披露或行业事件发生在相近日期？",
                )
            )
        turnover_percentile = _finite_number(
            activity.get("turnover_percentile_250d")
        )
        if turnover_percentile is not None and turnover_percentile >= 0.9:
            signals.append("普通换手率历史高位")
            candidates.append(
                _candidate(
                    "market_turnover",
                    82,
                    "普通换手率处于历史高位，筹码活跃度值得核验",
                    (
                        "普通换手率位于近250日的 "
                        f"{turnover_percentile:.1%} 分位；"
                        "它不等同于有效换手率。"
                    ),
                    "高换手是否持续出现，且能否取得更可靠的有效换手率口径？",
                )
            )
    if signals:
        return candidates, {
            "key": "market",
            "label": "市场状态",
            "state": "attention",
            "status_label": STATE_LABELS["attention"],
            "summary": "、".join(signals),
            "basis": "历史行情与交易活跃度的确定性门槛",
        }
    if status == "verified":
        return candidates, {
            "key": "market",
            "label": "市场状态",
            "state": "clear",
            "status_label": STATE_LABELS["clear"],
            "summary": "当前未触发涨停候选、明显放量或高换手门槛",
            "basis": "本次已核验行情区间",
        }
    return candidates, {
        "key": "market",
        "label": "市场状态",
        "state": "insufficient",
        "status_label": STATE_LABELS["insufficient"],
        "summary": "本次行情证据不足，不能判断交易异动",
        "basis": "公开行情源本次未完整取得",
    }


def _latest_high_attention_disclosure(
    announcements: Sequence[Mapping[str, object]] | None,
) -> Mapping[str, object] | None:
    if announcements is None:
        return None
    valid = [
        item
        for item in announcements
        if str(item.get("title", "")).strip()
        and is_allowed_disclosure_url(str(item.get("url", "")).strip())
    ]
    if not valid:
        return None
    latest = max(valid, key=lambda item: str(item.get("date", "")))
    return (
        latest
        if str(latest.get("attention", "")).strip() == "高"
        else None
    )


def _disclosure_candidate_and_pillar(
    disclosure_lane: Mapping[str, object] | None,
    announcements: Sequence[Mapping[str, object]] | None,
) -> tuple[_ConclusionCandidate | None, ConclusionPillar]:
    high_attention = _latest_high_attention_disclosure(announcements)
    if high_attention is not None:
        title = str(high_attention.get("title", "")).strip()
        return _candidate(
            "disclosure_high_attention",
            86,
            f"最近官方披露《{title}》被列为优先阅读材料",
            "“高关注”只安排阅读顺序，不代表公告内容属于利好或利空。",
            "这份公告改变了哪些已知事实、财务口径或风险边界？",
        ), {
            "key": "disclosure",
            "label": "官方动态",
            "state": "attention",
            "status_label": STATE_LABELS["attention"],
            "summary": f"优先阅读《{title}》",
            "basis": "已通过官方域名校验的披露标题与关注标签",
        }

    status = (
        str(disclosure_lane.get("status", "unavailable"))
        if disclosure_lane
        else "unavailable"
    )
    if status == "verified":
        return None, {
            "key": "disclosure",
            "label": "官方动态",
            "state": "clear",
            "status_label": STATE_LABELS["clear"],
            "summary": "当前未发现被标为高关注的官方披露",
            "basis": "本次已核验公告范围；不代表公司没有其他信息",
        }
    return None, {
        "key": "disclosure",
        "label": "官方动态",
        "state": "insufficient",
        "status_label": STATE_LABELS["insufficient"],
        "summary": "本次官方披露证据不足，不能判断最新动态",
        "basis": "没有使用新闻摘要或 AI 猜测替代官方披露",
    }


def build_research_conclusion(
    *,
    coverage_ratio: float,
    evidence_lanes: Sequence[Mapping[str, object]],
    market_activity: Mapping[str, object] | None = None,
    announcements: Sequence[Mapping[str, object]] | None = None,
    financial_history: Mapping[str, object] | None = None,
    financial_snapshot: Mapping[str, object] | None = None,
) -> ResearchConclusion:
    """Return the highest-priority supported research question.

    A higher internal priority means "review first", not "more risky" and not
    "more likely to rise".  The numeric priority is intentionally not exposed.
    """
    lanes = _lane_by_key(evidence_lanes)
    financial_candidate, financial_pillar = _financial_candidate_and_pillar(
        lanes.get("financial_history"),
        financial_history,
        financial_snapshot,
    )
    market_candidates, market_pillar = _market_candidates_and_pillar(
        lanes.get("market"),
        market_activity,
    )
    disclosure_candidate, disclosure_pillar = _disclosure_candidate_and_pillar(
        lanes.get("disclosures"),
        announcements,
    )
    candidates = [*market_candidates]
    if financial_candidate is not None:
        candidates.append(financial_candidate)
    if disclosure_candidate is not None:
        candidates.append(disclosure_candidate)

    if coverage_ratio < 0.5:
        primary = _candidate(
            "evidence_gap",
            100,
            "当前证据不足，最重要的结论是先补齐数据",
            (
                "本次取得的证据不足以形成可靠的一页式初步研究；"
                "系统不会把缺失值当作零，也不会用其他公司样例补写。"
            ),
            "应先补齐哪条缺失证据链，才能避免对公司形成片面判断？",
        )
    elif candidates:
        # Stable sort makes equal-priority rules reproducible across runs.
        primary = sorted(
            candidates,
            key=lambda item: (-item["priority"], item["key"]),
        )[0]
    elif lanes.get("financial_history", {}).get("status") != "verified":
        primary = _candidate(
            "financial_gap",
            70,
            "已形成初步研究，但财务证据仍是当前最大缺口",
            (
                "市场与披露信息可以帮助安排研究顺序，但没有已核验的"
                "多年财务趋势时，不能形成完整的公司基本面判断。"
            ),
            "能否从最新年报生成并人工复核公司财务快照？",
        )
    elif coverage_ratio >= 0.8:
        primary = _candidate(
            "no_rule_triggered",
            20,
            "当前公开证据未触发预设重大异常，继续跟踪变化即可",
            (
                "这只表示本次确定性规则没有发现方向背离或交易异动，"
                "不代表公司质量良好，也不预测未来收益。"
            ),
            "下一次财报或官方披露是否改变当前已知事实？",
        )
    else:
        primary = _candidate(
            "initial_research",
            10,
            "当前可形成初步研究，但仍需补齐部分证据",
            "现有证据足以安排下一步阅读顺序，但不足以支持完整判断。",
            "哪条部分可用或缺失的证据链最容易先完成核验？",
        )

    verified_count = sum(
        str(lane.get("status")) == "verified" for lane in evidence_lanes
    )
    partial_count = sum(
        str(lane.get("status")) == "partial" for lane in evidence_lanes
    )
    unavailable_count = sum(
        str(lane.get("status")) == "unavailable" for lane in evidence_lanes
    )
    return {
        "headline": primary["headline"],
        "explanation": primary["explanation"],
        "next_question": primary["next_question"],
        "evidence_summary": (
            f"{len(evidence_lanes)} 条证据链中，{verified_count} 条已核验、"
            f"{partial_count} 条部分可用、{unavailable_count} 条暂不可用。"
        ),
        "primary_key": primary["key"],
        "pillars": [financial_pillar, market_pillar, disclosure_pillar],
    }
