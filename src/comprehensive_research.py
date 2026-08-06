"""Build one auditable company-research brief from existing evidence.

The coordinator in this module does not fetch data and does not call an LLM.
It receives already validated public-market, disclosure, and financial inputs,
then records what is available, what is missing, and which product page should
be used for the next verification step.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Literal, TypedDict

from src.china_stock import (
    CompanyIdentity,
    MarketActivityEvidence,
    MarketMetrics,
    is_allowed_disclosure_url,
)
from src.financial_history import FinancialHistoryResult


EvidenceStatus = Literal["verified", "partial", "unavailable"]


class EvidenceLane(TypedDict):
    """One bounded evidence lane in the comprehensive research run."""

    key: str
    label: str
    status: EvidenceStatus
    summary: str
    source: str
    as_of_date: str | None
    source_url: str | None
    limitation: str


class ResearchFinding(TypedDict):
    """One deterministic observation with its calculation basis."""

    category: str
    headline: str
    statement: str
    basis: str
    status: EvidenceStatus
    source_url: str | None


class ResearchAction(TypedDict):
    """One suggested verification action inside the product."""

    priority: int
    page: str
    label: str
    reason: str


class ResearchTraceStep(TypedDict):
    """One explicit handoff in the bounded research workflow."""

    sequence: int
    agent: str
    status: EvidenceStatus
    task: str
    output: str


class ComprehensiveResearchBrief(TypedDict):
    """Evidence-first output from one company research run."""

    company: CompanyIdentity
    generated_on: str
    coverage_ratio: float
    coverage_label: str
    verified_lane_count: int
    partial_lane_count: int
    unavailable_lane_count: int
    evidence_lanes: list[EvidenceLane]
    findings: list[ResearchFinding]
    actions: list[ResearchAction]
    trace: list[ResearchTraceStep]
    limitations: list[str]


def _as_iso_date(value: object) -> str | None:
    """Normalise supported public-source dates without guessing."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def _format_percent(value: object) -> str:
    """Format an optional ratio while keeping missing evidence explicit."""
    if value is None:
        return "数据不足"
    try:
        return f"{float(value):.1%}"
    except (TypeError, ValueError):
        return "数据不足"


def _format_multiple(value: object) -> str:
    if value is None:
        return "数据不足"
    try:
        return f"{float(value):.2f} 倍"
    except (TypeError, ValueError):
        return "数据不足"


def _safe_official_url(value: object) -> str | None:
    url = str(value or "").strip()
    return url if url and is_allowed_disclosure_url(url) else None


def _latest_disclosure(
    announcements: Sequence[Mapping[str, object]] | None,
) -> Mapping[str, object] | None:
    """Return the newest dated official disclosure from validated inputs."""
    if announcements is None:
        return None
    valid: list[tuple[str, Mapping[str, object]]] = []
    for announcement in announcements:
        published_date = _as_iso_date(announcement.get("date"))
        title = str(announcement.get("title", "")).strip()
        source_url = _safe_official_url(announcement.get("url"))
        if published_date and title and source_url:
            valid.append((published_date, announcement))
    if not valid:
        return None
    return max(valid, key=lambda item: (item[0], str(item[1].get("title"))))[1]


def _market_lane(
    metrics: MarketMetrics | None,
    activity: MarketActivityEvidence | None,
    market_source: str,
) -> EvidenceLane:
    if metrics is not None and activity is not None:
        return {
            "key": "market",
            "label": "行情与活跃度",
            "status": "verified",
            "summary": (
                f"已核验至 {metrics['latest_date']}，"
                f"共 {metrics['observations']} 个有效交易日。"
            ),
            "source": market_source or "公开行情适配器",
            "as_of_date": metrics["latest_date"],
            "source_url": None,
            "limitation": "历史行情只描述已经发生的市场表现。",
        }
    if metrics is not None or activity is not None:
        latest_date = (
            metrics["latest_date"]
            if metrics is not None
            else activity["latest_date"] if activity is not None else None
        )
        return {
            "key": "market",
            "label": "行情与活跃度",
            "status": "partial",
            "summary": "已取得部分行情证据，但完整统计未全部生成。",
            "source": market_source or "公开行情适配器",
            "as_of_date": latest_date,
            "source_url": None,
            "limitation": "缺失字段不会按零处理，也不会由 AI 补写。",
        }
    return {
        "key": "market",
        "label": "行情与活跃度",
        "status": "unavailable",
        "summary": "本次未取得可验证的历史行情。",
        "source": market_source or "公开行情适配器",
        "as_of_date": None,
        "source_url": None,
        "limitation": "需要稍后重试公开行情源。",
    }


def _disclosure_lane(
    announcements: Sequence[Mapping[str, object]] | None,
    status_text: str,
) -> EvidenceLane:
    latest = _latest_disclosure(announcements)
    if announcements is None:
        return {
            "key": "disclosures",
            "label": "官方公告",
            "status": "unavailable",
            "summary": status_text or "官方公告源本次未完成核验。",
            "source": "巨潮资讯 / 交易所公开披露",
            "as_of_date": None,
            "source_url": None,
            "limitation": "系统没有使用新闻摘要或 AI 猜测替代。",
        }
    if latest is None:
        return {
            "key": "disclosures",
            "label": "官方公告",
            "status": "verified",
            "summary": f"查询范围已核验，取得 {len(announcements)} 条可展示公告。",
            "source": "巨潮资讯 / 交易所公开披露",
            "as_of_date": None,
            "source_url": None,
            "limitation": "没有可展示公告不等于公司没有其他公开信息。",
        }
    return {
        "key": "disclosures",
        "label": "官方公告",
        "status": "verified",
        "summary": (
            f"已核验 {len(announcements)} 条；最新为《"
            f"{str(latest.get('title', '')).strip()}》。"
        ),
        "source": "巨潮资讯 / 交易所公开披露",
        "as_of_date": _as_iso_date(latest.get("date")),
        "source_url": _safe_official_url(latest.get("url")),
        "limitation": "标题关注程度只安排阅读顺序，不代表利好或利空。",
    }


def _annual_report_lane(
    latest_annual_report: Mapping[str, object] | None,
) -> EvidenceLane:
    if latest_annual_report is None:
        return {
            "key": "annual_report",
            "label": "最新年度报告",
            "status": "unavailable",
            "summary": "查询范围内尚未定位到可验证的完整年度报告。",
            "source": "官方年度报告入口",
            "as_of_date": None,
            "source_url": None,
            "limitation": "可以在年报页面手工上传公开 PDF 继续分析。",
        }
    source_url = _safe_official_url(latest_annual_report.get("url"))
    status: EvidenceStatus = "verified" if source_url else "partial"
    return {
        "key": "annual_report",
        "label": "最新年度报告",
        "status": status,
        "summary": str(latest_annual_report.get("title", "完整年度报告")).strip(),
        "source": "官方年度报告",
        "as_of_date": _as_iso_date(latest_annual_report.get("date")),
        "source_url": source_url,
        "limitation": (
            "报告已定位；具体结论仍需引用原文页码。"
            if source_url
            else "报告链接尚未通过官方域名校验。"
        ),
    }


def _financial_lane(
    financial_history: FinancialHistoryResult | None,
    company: CompanyIdentity,
    financial_snapshot: Mapping[str, object] | None,
) -> EvidenceLane:
    points = financial_history["points"] if financial_history else []
    if len(points) >= 2:
        latest = points[-1]
        return {
            "key": "financial_history",
            "label": "已核验财务历史",
            "status": "verified",
            "summary": (
                f"覆盖 {len(points)} 个年度，最新核验年度为 "
                f"{latest['period_year']} 年。"
            ),
            "source": "逐页核验年度报告数据集",
            "as_of_date": financial_history["as_of_date"],
            "source_url": _safe_official_url(latest["source_url"]),
            "limitation": "仅已完成逐页核验的公司会显示多年财务趋势。",
        }
    if len(points) == 1:
        latest = points[-1]
        return {
            "key": "financial_history",
            "label": "已核验财务历史",
            "status": "partial",
            "summary": f"当前只有 {latest['period_year']} 年一组已核验数据。",
            "source": "逐页核验年度报告数据集",
            "as_of_date": financial_history["as_of_date"],
            "source_url": _safe_official_url(latest["source_url"]),
            "limitation": "单一年度不足以形成可靠的多年趋势。",
        }
    snapshot = _matching_financial_snapshot(company, financial_snapshot)
    if snapshot is not None:
        report = snapshot["report"]
        report_year = report.get("report_year")
        ready = (
            snapshot.get("status") == "ready_for_human_review"
            and _snapshot_has_reviewable_metrics(snapshot)
        )
        return {
            "key": "financial_history",
            "label": "单期财务快照（待复核）",
            "status": "partial",
            "summary": (
                f"已复用 {report_year} 年最新年报的单期自动提取候选；"
                + (
                    "五项核心金额可进入人工复核。"
                    if ready
                    else "自动检查未全部通过，暂不输出金额观察。"
                )
            ),
            "source": "最新完整年度报告自动提取候选",
            "as_of_date": _as_iso_date(report.get("published_date")),
            "source_url": _safe_official_url(report.get("source_url")),
            "limitation": (
                "仅为单期自动提取候选，未经人工复核，不等于逐页核验的"
                "多年财务历史。"
            ),
        }
    return {
        "key": "financial_history",
        "label": "已核验财务历史",
        "status": "unavailable",
        "summary": "该公司尚未接入逐页核验的多年财务基准。",
        "source": "逐页核验年度报告数据集",
        "as_of_date": None,
        "source_url": None,
        "limitation": "可以先使用官方年报解析，不会套用其他公司的数据。",
    }


def _matching_financial_snapshot(
    company: CompanyIdentity,
    financial_snapshot: Mapping[str, object] | None,
) -> Mapping[str, object] | None:
    """Accept only one same-company snapshot backed by an official report."""
    if not isinstance(financial_snapshot, Mapping):
        return None
    snapshot_company = financial_snapshot.get("company")
    report = financial_snapshot.get("report")
    status = financial_snapshot.get("status")
    if not isinstance(snapshot_company, Mapping) or not isinstance(
        report, Mapping
    ):
        return None
    if snapshot_company.get("canonical_code") != company["canonical_code"]:
        return None
    if status not in {"ready_for_human_review", "needs_review"}:
        return None
    if _safe_official_url(report.get("source_url")) is None:
        return None
    if not _as_iso_date(report.get("published_date")):
        return None
    try:
        report_year = int(report["report_year"])
    except (KeyError, TypeError, ValueError):
        return None
    if report_year < 1990 or report_year > date.today().year:
        return None
    return financial_snapshot


def _finite_number(value: object) -> float | None:
    """Normalise one candidate number without turning missing data into zero."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _snapshot_metric_map(
    snapshot: Mapping[str, object],
) -> dict[str, Mapping[str, object]]:
    raw_metrics = snapshot.get("metrics")
    if not isinstance(raw_metrics, Sequence) or isinstance(
        raw_metrics, (str, bytes)
    ):
        return {}
    metrics: dict[str, Mapping[str, object]] = {}
    for metric in raw_metrics:
        if not isinstance(metric, Mapping):
            continue
        key = str(metric.get("key", "")).strip()
        if key:
            metrics[key] = metric
    return metrics


def _format_snapshot_amount(value: object) -> str:
    number = _finite_number(value)
    return "数据不足" if number is None else f"¥{number / 100_000_000:,.2f}亿元"


def _format_snapshot_pages(value: object) -> str:
    if not isinstance(value, Mapping):
        return "页码待核验"
    try:
        start = int(value["start"])
        end = int(value["end"])
    except (KeyError, TypeError, ValueError):
        return "页码待核验"
    if start <= 0 or end < start:
        return "页码待核验"
    return f"第{start}页" if start == end else f"第{start}–{end}页"


def _snapshot_has_reviewable_metrics(
    snapshot: Mapping[str, object],
) -> bool:
    """Require all five finite values and usable PDF page provenance."""
    metrics = _snapshot_metric_map(snapshot)
    required_keys = {
        "revenue",
        "net_profit",
        "operating_cash_flow",
        "total_assets",
        "total_liabilities",
    }
    return required_keys.issubset(metrics) and all(
        _finite_number(metrics[key].get("current_yuan")) is not None
        and _format_snapshot_pages(metrics[key].get("pages"))
        != "页码待核验"
        for key in required_keys
    )


def _market_findings(
    metrics: MarketMetrics | None,
    activity: MarketActivityEvidence | None,
) -> list[ResearchFinding]:
    findings: list[ResearchFinding] = []
    if metrics is not None:
        findings.append(
            {
                "category": "市场表现",
                "headline": f"行情截止 {metrics['latest_date']}",
                "statement": (
                    f"最新收盘价 ¥{metrics['latest_close']:,.2f}；"
                    f"近20交易日收益 {_format_percent(metrics['return_20d'])}；"
                    f"年化历史波动率 {_format_percent(metrics['annualised_volatility'])}；"
                    f"区间最大回撤 {_format_percent(metrics['max_drawdown'])}。"
                ),
                "basis": "全部指标由历史收盘价通过 Python 确定性计算。",
                "status": "verified",
                "source_url": None,
            }
        )
    if activity is not None:
        signals: list[str] = []
        if activity["limit_up_status"] == "涨停候选":
            signals.append("涨停候选")
        if (
            activity["volume_ratio_20d"] is not None
            and activity["volume_ratio_20d"] >= 2
        ):
            signals.append("明显放量")
        if (
            activity["turnover_percentile_250d"] is not None
            and activity["turnover_percentile_250d"] >= 0.9
        ):
            signals.append("普通换手率历史高位")
        signal_text = "、".join(signals) if signals else "未触发当前三项异动门槛"
        available_count = sum(
            value is not None
            for value in (
                activity["daily_return"],
                activity["volume_ratio_20d"],
                activity["turnover_percentile_250d"],
            )
        )
        findings.append(
            {
                "category": "交易活跃度",
                "headline": signal_text,
                "statement": (
                    f"最新日涨跌幅 {_format_percent(activity['daily_return'])}；"
                    f"成交量为前20日中位数的 "
                    f"{_format_multiple(activity['volume_ratio_20d'])}；"
                    f"普通换手率历史分位 "
                    f"{_format_percent(activity['turnover_percentile_250d'])}。"
                ),
                "basis": (
                    f"三项中有 {available_count}/3 项具备可判断证据；"
                    "普通换手率不等同于有效换手率。"
                ),
                "status": "verified" if available_count == 3 else "partial",
                "source_url": None,
            }
        )
    return findings


def _disclosure_findings(
    announcements: Sequence[Mapping[str, object]] | None,
    latest_annual_report: Mapping[str, object] | None,
) -> list[ResearchFinding]:
    findings: list[ResearchFinding] = []
    latest = _latest_disclosure(announcements)
    if latest is not None:
        title = str(latest.get("title", "")).strip()
        category = str(latest.get("category", "其他公告")).strip()
        attention = str(latest.get("attention", "低")).strip()
        findings.append(
            {
                "category": "官方披露",
                "headline": title,
                "statement": (
                    f"公告日期 {_as_iso_date(latest.get('date'))}；"
                    f"类别 {category or '其他公告'}；"
                    f"阅读关注程度 {attention or '低'}。"
                ),
                "basis": "来自已通过域名校验的官方披露链接。",
                "status": "verified",
                "source_url": _safe_official_url(latest.get("url")),
            }
        )
    if latest_annual_report is not None:
        findings.append(
            {
                "category": "年度报告",
                "headline": str(
                    latest_annual_report.get("title", "最新完整年度报告")
                ).strip(),
                "statement": (
                    "已定位完整年度报告入口，可进入页码保留的解析流程。"
                ),
                "basis": (
                    f"公告日期 {_as_iso_date(latest_annual_report.get('date')) or '待核验'}。"
                ),
                "status": (
                    "verified"
                    if _safe_official_url(latest_annual_report.get("url"))
                    else "partial"
                ),
                "source_url": _safe_official_url(latest_annual_report.get("url")),
            }
        )
    return findings


def _financial_finding(
    financial_history: FinancialHistoryResult | None,
    company: CompanyIdentity,
    financial_snapshot: Mapping[str, object] | None,
) -> ResearchFinding | None:
    points = financial_history["points"] if financial_history else []
    if points:
        latest = points[-1]
        return {
            "category": "财务质量",
            "headline": f"{latest['period_year']} 年已核验财务快照",
            "statement": (
                f"营业收入同比 {_format_percent(latest['revenue_growth'])}；"
                f"归母净利润同比 {_format_percent(latest['net_profit_growth'])}；"
                f"净利率 {_format_percent(latest['net_margin'])}；"
                f"经营现金流/净利润 {latest['cash_conversion']:.2f} 倍；"
                f"资产负债率 {_format_percent(latest['liabilities_to_assets'])}。"
            ),
            "basis": (
                f"利润表/摘要页 {latest['summary_page']}；"
                f"资产负债表页 {latest['balance_sheet_page']}；"
                f"证据等级 {latest['evidence_grade']}。"
            ),
            "status": "verified" if len(points) >= 2 else "partial",
            "source_url": _safe_official_url(latest["source_url"]),
        }

    snapshot = _matching_financial_snapshot(company, financial_snapshot)
    if (
        snapshot is None
        or snapshot.get("status") != "ready_for_human_review"
        or not _snapshot_has_reviewable_metrics(snapshot)
    ):
        return None
    metrics = _snapshot_metric_map(snapshot)
    required_keys = (
        "revenue",
        "net_profit",
        "operating_cash_flow",
        "total_assets",
        "total_liabilities",
    )
    report = snapshot["report"]
    ratios = snapshot.get("ratios")
    ratio_values = ratios if isinstance(ratios, Mapping) else {}
    page_basis = "；".join(
        f"{metrics[key].get('label', key)}："
        f"{metrics[key].get('statement', '报表')}"
        f"{_format_snapshot_pages(metrics[key].get('pages'))}"
        for key in required_keys
    )
    return {
        "category": "财务快照",
        "headline": f"{report.get('report_year')} 年单期候选（待人工复核）",
        "statement": (
            "营业收入 "
            f"{_format_snapshot_amount(metrics['revenue'].get('current_yuan'))}；"
            "净利润 "
            f"{_format_snapshot_amount(metrics['net_profit'].get('current_yuan'))}；"
            "经营活动现金流量净额 "
            f"{_format_snapshot_amount(metrics['operating_cash_flow'].get('current_yuan'))}；"
            "资产总额 "
            f"{_format_snapshot_amount(metrics['total_assets'].get('current_yuan'))}；"
            "负债总额 "
            f"{_format_snapshot_amount(metrics['total_liabilities'].get('current_yuan'))}。"
            f"净利率 {_format_percent(ratio_values.get('net_profit_margin'))}；"
            "经营现金流/净利润 "
            f"{_format_multiple(ratio_values.get('operating_cash_conversion'))}；"
            f"资产负债率 {_format_percent(ratio_values.get('liabilities_to_assets'))}。"
        ),
        "basis": f"{page_basis}；自动提取候选，未经人工复核。",
        "status": "partial",
        "source_url": _safe_official_url(report.get("source_url")),
    }


def _build_actions(
    lanes: list[EvidenceLane],
    activity: MarketActivityEvidence | None,
) -> list[ResearchAction]:
    lane_by_key = {lane["key"]: lane for lane in lanes}
    actions: list[ResearchAction] = []
    if activity is not None:
        triggered = (
            activity["limit_up_status"] == "涨停候选"
            or (
                activity["volume_ratio_20d"] is not None
                and activity["volume_ratio_20d"] >= 2
            )
            or (
                activity["turnover_percentile_250d"] is not None
                and activity["turnover_percentile_250d"] >= 0.9
            )
        )
        actions.append(
            {
                "priority": 1 if triggered else 3,
                "page": "anomaly",
                "label": "进入市场异动 Agent",
                "reason": (
                    "至少一项交易活跃度门槛已触发，需要按日期核验公告。"
                    if triggered
                    else "复核历史交易活跃度与候选日期。"
                ),
            }
        )
    if lane_by_key["annual_report"]["status"] != "verified":
        actions.append(
            {
                "priority": 1,
                "page": "annual",
                "label": "补充年度报告证据",
                "reason": "最新完整年报入口尚未通过本次自动核验。",
            }
        )
    else:
        actions.append(
            {
                "priority": 2,
                "page": "annual",
                "label": "进入年报与证据分析",
                "reason": "使用已定位的官方报告继续做页码级问答和计算。",
            }
        )
    if lane_by_key["financial_history"]["status"] == "verified":
        actions.append(
            {
                "priority": 2,
                "page": "financial_trend",
                "label": "查看财务趋势实验室",
                "reason": "已有至少两个年度的逐页核验财务数据。",
            }
        )
    elif lane_by_key["financial_history"]["source"] == (
        "最新完整年度报告自动提取候选"
    ):
        actions.append(
            {
                "priority": 2,
                "page": "financial_snapshot",
                "label": "复核并更新财务快照",
                "reason": (
                    "本次只复用了单期自动提取候选，仍需核对原文"
                    "页码与口径。"
                ),
            }
        )
    elif lane_by_key["financial_history"]["status"] == "unavailable":
        actions.append(
            {
                "priority": 2,
                "page": "financial_snapshot",
                "label": "生成最新年报财务快照",
                "reason": (
                    "当前没有该公司的财务数据，可按需生成单期候选"
                    "后重新运行。"
                ),
            }
        )
    else:
        actions.append(
            {
                "priority": 2,
                "page": "financial_trend",
                "label": "查看财务覆盖边界",
                "reason": "当前多年财务历史仍不完整，不能套用其他公司数据。",
            }
        )
    actions.append(
        {
            "priority": 3,
            "page": "market",
            "label": "查看完整 K 线",
            "reason": "核对本简报所使用的价格、成交量和统计区间。",
        }
    )
    return sorted(actions, key=lambda item: (item["priority"], item["label"]))


def _build_trace(lanes: list[EvidenceLane]) -> list[ResearchTraceStep]:
    definitions = {
        "identity": ("Identity Agent", "核验股票代码、交易所和公司名称"),
        "market": ("Market Evidence Agent", "计算行情与交易活跃度"),
        "disclosures": ("Disclosure Agent", "筛选官方公告并保留原始链接"),
        "annual_report": ("Report Agent", "定位最新完整年度报告"),
        "financial_history": (
            "Financial Evidence Agent",
            "优先读取逐页核验财务历史，否则复用当前会话的单期候选",
        ),
    }
    trace: list[ResearchTraceStep] = []
    for lane in lanes:
        agent, task = definitions[lane["key"]]
        trace.append(
            {
                "sequence": len(trace) + 1,
                "agent": agent,
                "status": lane["status"],
                "task": task,
                "output": lane["summary"],
            }
        )
    trace.append(
        {
            "sequence": len(trace) + 1,
            "agent": "Research Coordinator",
            "status": (
                "verified"
                if sum(lane["status"] == "verified" for lane in lanes) >= 4
                else "partial"
            ),
            "task": "汇总证据覆盖、确定性观察与下一步核验任务",
            "output": "没有把缺失数据替换为零，也没有生成投资建议。",
        }
    )
    return trace


def build_comprehensive_research_brief(
    company: CompanyIdentity,
    *,
    market_metrics: MarketMetrics | None = None,
    market_activity: MarketActivityEvidence | None = None,
    market_source: str = "",
    turnover_source: str = "",
    announcements: Sequence[Mapping[str, object]] | None = None,
    announcements_status: str = "",
    latest_annual_report: Mapping[str, object] | None = None,
    financial_history: FinancialHistoryResult | None = None,
    financial_snapshot: Mapping[str, object] | None = None,
    generated_on: date | None = None,
    data_errors: Sequence[str] = (),
) -> ComprehensiveResearchBrief:
    """Combine independent evidence lanes without producing a forecast."""
    run_date = generated_on or date.today()
    identity_lane: EvidenceLane = {
        "key": "identity",
        "label": "上市公司身份",
        "status": "verified",
        "summary": (
            f"{company['name']}｜{company['canonical_code']}｜"
            f"{company['exchange_name']}。"
        ),
        "source": "A股公司目录与交易所代码规则",
        "as_of_date": run_date.isoformat(),
        "source_url": None,
        "limitation": (
            "公司名称待核验时，页面会单独提示，不以代码推测名称。"
        ),
    }
    lanes = [
        identity_lane,
        _market_lane(market_metrics, market_activity, market_source),
        _disclosure_lane(announcements, announcements_status),
        _annual_report_lane(latest_annual_report),
        _financial_lane(financial_history, company, financial_snapshot),
    ]
    status_points = {"verified": 1.0, "partial": 0.5, "unavailable": 0.0}
    coverage_ratio = sum(status_points[lane["status"]] for lane in lanes) / len(lanes)
    if coverage_ratio >= 0.8:
        coverage_label = "证据覆盖较完整"
    elif coverage_ratio >= 0.5:
        coverage_label = "可生成初步研究"
    else:
        coverage_label = "证据不足，优先补充来源"

    findings = [
        *_market_findings(market_metrics, market_activity),
        *_disclosure_findings(announcements, latest_annual_report),
    ]
    financial_finding = _financial_finding(
        financial_history,
        company,
        financial_snapshot,
    )
    if financial_finding is not None:
        findings.append(financial_finding)

    limitations = [
        "证据覆盖率衡量本次取得的数据范围，不代表公司质量或结论正确概率。",
        "历史行情、涨停候选、成交量和换手率都不能用于预测未来收益。",
        "公告与市场异动时间接近不能证明因果关系。",
        "本简报不构成买入、卖出或持有建议。",
    ]
    limitations.extend(str(error).strip() for error in data_errors if str(error).strip())
    if turnover_source:
        limitations.append(f"普通换手率来源：{turnover_source}；不等同于有效换手率。")
    if lanes[-1]["source"] == "最新完整年度报告自动提取候选":
        limitations.append(
            "单期财务快照由程序从最新完整年报自动提取，未经人工复核；"
            "它不会替代逐页核验的多年财务历史。"
        )

    return {
        "company": company,
        "generated_on": run_date.isoformat(),
        "coverage_ratio": coverage_ratio,
        "coverage_label": coverage_label,
        "verified_lane_count": sum(lane["status"] == "verified" for lane in lanes),
        "partial_lane_count": sum(lane["status"] == "partial" for lane in lanes),
        "unavailable_lane_count": sum(
            lane["status"] == "unavailable" for lane in lanes
        ),
        "evidence_lanes": lanes,
        "findings": findings,
        "actions": _build_actions(lanes, market_activity),
        "trace": _build_trace(lanes),
        "limitations": limitations,
    }
