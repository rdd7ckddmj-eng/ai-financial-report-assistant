"""Deterministic explanation bridge for verified financial anomalies.

The module separates three layers that must not be blurred together:
the trend signal, the annual-report cash-flow reconciliation, and unresolved
business explanations.  It does not forecast results or produce investment
recommendations.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Literal, TypedDict
from urllib.parse import urlparse

from src.financial_history import ALLOWED_REPORT_HOSTS, FinancialTrendPoint


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FINANCIAL_ANOMALY_EVIDENCE_PATH = (
    PROJECT_ROOT / "data" / "verified" / "financial_anomaly_evidence.csv"
)
BYD_FINANCIAL_ANOMALY_EVIDENCE_PATH = (
    PROJECT_ROOT
    / "data"
    / "verified"
    / "byd_financial_anomaly_evidence.csv"
)
FINANCIAL_ANOMALY_EVIDENCE_PATHS = (
    FINANCIAL_ANOMALY_EVIDENCE_PATH,
    BYD_FINANCIAL_ANOMALY_EVIDENCE_PATH,
)
REQUIRED_FIELDS = {
    "company_code",
    "company_name",
    "canonical_code",
    "period_year",
    "comparison_year",
    "report_title",
    "source_url",
    "source_page",
    "component_code",
    "component_label",
    "current_value",
    "comparison_value",
    "evidence_grade",
    "verification_status",
    "notes",
}


class CashFlowBridgeComponent(TypedDict):
    """One verified row from an annual-report cash-flow reconciliation."""

    company_code: str
    company_name: str
    canonical_code: str
    period_year: int
    comparison_year: int
    report_title: str
    source_url: str
    source_page: int
    component_code: str
    component_label: str
    current_value: float
    comparison_value: float
    evidence_grade: Literal["A"]
    verification_status: Literal["verified"]
    notes: str


class CashFlowBridgeDriver(TypedDict):
    """One component ranked by its contribution to the year-on-year change."""

    rank: int
    component_code: str
    component_label: str
    current_value: float
    comparison_value: float
    change_contribution: float
    absolute_change_contribution: float
    direction: Literal["拉低", "支撑", "不变"]


class FinancialAnomalyReview(TypedDict):
    """Auditable signal, bridge, and research-boundary result."""

    company_code: str
    company_name: str
    canonical_code: str
    period_year: int
    comparison_year: int
    revenue_growth: float
    attributable_net_profit_growth: float
    operating_cash_flow_growth: float
    signal_detected: bool
    signal_label: str
    operating_cash_flow_current: float
    operating_cash_flow_comparison: float
    operating_cash_flow_change: float
    bridge_current_total: float
    bridge_comparison_total: float
    bridge_change_total: float
    reconciliation_passed: bool
    drivers: list[CashFlowBridgeDriver]
    confirmed_findings: list[str]
    unresolved_questions: list[str]
    report_title: str
    source_url: str
    source_page: int
    evidence_grade: str
    verification_status: str
    limitation: str


def _positive_int(value: object, field_name: str) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} 不是有效整数。") from error
    if parsed <= 0:
        raise ValueError(f"{field_name} 必须大于零。")
    return parsed


def _finite_float(value: object, field_name: str) -> float:
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} 不是有效数字。") from error
    if not math.isfinite(parsed):
        raise ValueError(f"{field_name} 必须是有限数字。")
    return parsed


def _validate_row(row: dict[str, str]) -> CashFlowBridgeComponent:
    company_code = str(row["company_code"]).strip()
    company_name = str(row["company_name"]).strip()
    canonical_code = str(row["canonical_code"]).strip().upper()
    if not company_code.isdigit() or len(company_code) != 6:
        raise ValueError("异常证据中的股票代码必须是6位数字。")
    if not company_name or not str(row["report_title"]).strip():
        raise ValueError("异常证据必须保留公司名称和报告名称。")
    if canonical_code not in {f"{company_code}.SZ", f"{company_code}.SH"}:
        raise ValueError("异常证据中的标准股票代码不一致。")

    source_url = str(row["source_url"]).strip()
    parsed_url = urlparse(source_url)
    if (
        parsed_url.scheme != "https"
        or parsed_url.hostname not in ALLOWED_REPORT_HOSTS
    ):
        raise ValueError("异常证据必须使用允许的官方 HTTPS 来源。")
    if row["evidence_grade"] != "A":
        raise ValueError("异常证据必须保留 A 级证据。")
    if row["verification_status"] != "verified":
        raise ValueError("未核验数据不能进入财务异常解释。")

    period_year = _positive_int(row["period_year"], "period_year")
    comparison_year = _positive_int(
        row["comparison_year"],
        "comparison_year",
    )
    if comparison_year >= period_year:
        raise ValueError("对比年度必须早于当期年度。")
    component_code = str(row["component_code"]).strip()
    component_label = str(row["component_label"]).strip()
    if not component_code or not component_label:
        raise ValueError("现金流调节项代码和名称不能为空。")

    return {
        "company_code": company_code,
        "company_name": company_name,
        "canonical_code": canonical_code,
        "period_year": period_year,
        "comparison_year": comparison_year,
        "report_title": str(row["report_title"]).strip(),
        "source_url": source_url,
        "source_page": _positive_int(row["source_page"], "source_page"),
        "component_code": component_code,
        "component_label": component_label,
        "current_value": _finite_float(
            row["current_value"],
            "current_value",
        ),
        "comparison_value": _finite_float(
            row["comparison_value"],
            "comparison_value",
        ),
        "evidence_grade": "A",
        "verification_status": "verified",
        "notes": str(row["notes"]).strip(),
    }


def load_financial_anomaly_evidence(
    path: Path = FINANCIAL_ANOMALY_EVIDENCE_PATH,
) -> list[CashFlowBridgeComponent]:
    """Load a controlled cash-flow bridge and reject mixed evidence."""
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            missing = REQUIRED_FIELDS - set(reader.fieldnames or [])
            if missing:
                raise ValueError(
                    "财务异常证据缺少字段："
                    + "、".join(sorted(missing))
                )
            rows = list(reader)
    except OSError as error:
        raise ValueError("无法读取财务异常证据。") from error
    if not rows:
        raise ValueError("财务异常证据为空。")

    components = [_validate_row(row) for row in rows]
    identity_fields = (
        "company_code",
        "company_name",
        "canonical_code",
        "period_year",
        "comparison_year",
        "report_title",
        "source_url",
        "source_page",
    )
    for field_name in identity_fields:
        if len({item[field_name] for item in components}) != 1:
            raise ValueError("同一异常案例中混入了不一致的证据。")
    component_codes = [item["component_code"] for item in components]
    if len(component_codes) != len(set(component_codes)):
        raise ValueError("现金流调节项不能重复。")
    return components


def load_financial_anomaly_cases(
    paths: Sequence[Path] = FINANCIAL_ANOMALY_EVIDENCE_PATHS,
) -> list[list[CashFlowBridgeComponent]]:
    """Load separate controlled cases without allowing duplicate identities."""
    cases: list[list[CashFlowBridgeComponent]] = []
    seen: set[tuple[str, int, int]] = set()
    for path in paths:
        components = load_financial_anomaly_evidence(path)
        first = components[0]
        identity = (
            first["company_code"],
            first["period_year"],
            first["comparison_year"],
        )
        if identity in seen:
            raise ValueError("财务异常案例不能重复。")
        seen.add(identity)
        cases.append(components)
    if not cases:
        raise ValueError("财务异常案例目录为空。")
    return cases


def _growth(current: float, comparison: float) -> float:
    if comparison == 0:
        raise ValueError("对比年度基数为零，无法计算同比。")
    return current / comparison - 1


def _close(first: float, second: float) -> bool:
    tolerance = max(1.0, abs(second) * 1e-10)
    return abs(first - second) <= tolerance


def _format_percent(value: float) -> str:
    return f"{value:.1%}"


def _format_100m(value: float) -> str:
    return f"{value / 100_000_000:,.2f} 亿元"


def _build_unresolved_questions(
    drivers: Sequence[CashFlowBridgeDriver],
) -> list[str]:
    """Turn bridge directions into questions, never unsupported causes."""
    by_code = {item["component_code"]: item for item in drivers}
    questions: list[str] = []
    payables = by_code.get("operating_payables")
    if payables and payables["change_contribution"] < 0:
        questions.append(
            "经营性应付项目增加额为什么明显低于上年？"
            "需进一步拆分应付账款、应付票据、合同负债、"
            "其他经营性应付与结算时点。"
        )
    elif payables:
        questions.append(
            "经营性应付项目对现金流的同比支撑为什么增强？"
            "需进一步拆分应付账款、应付票据、合同负债、"
            "其他经营性应付与结算时点。"
        )
    questions.append(
        (
            "该变化是否受业务结构、并表范围或供应链结算政策影响？"
            "需回到相关科目附注和管理层讨论核查。"
        )
    )

    inventory = by_code.get("inventory_change")
    receivables = by_code.get("operating_receivables")
    if inventory and inventory["change_contribution"] < 0:
        questions.append(
            "存货增加对经营现金流的占用为什么扩大？"
            "需核查原材料、在产品、产成品、周转速度与减值附注。"
        )
    elif inventory:
        questions.append(
            "存货对经营现金流的同比改善是否可持续？"
            "需结合存货结构、周转速度与减值附注继续跟踪。"
        )

    if receivables and receivables["change_contribution"] < 0:
        questions.append(
            "经营性应收项目的现金占用为什么扩大？"
            "需核查应收账款、应收票据、合同资产与客户结算条款。"
        )
    elif receivables:
        questions.append(
            "经营性应收项目对现金流的同比改善是否可持续？"
            "需结合应收结构、账龄与结算条款继续跟踪。"
        )
    return questions


def build_financial_anomaly_review(
    points: Sequence[FinancialTrendPoint],
    components: Sequence[CashFlowBridgeComponent],
) -> FinancialAnomalyReview:
    """Build a verified anomaly explanation without inventing root causes."""
    if not components:
        raise ValueError("财务异常解释至少需要一项调节证据。")
    first = components[0]
    for item in components:
        if (
            item["company_code"] != first["company_code"]
            or item["period_year"] != first["period_year"]
            or item["comparison_year"] != first["comparison_year"]
            or item["source_url"] != first["source_url"]
        ):
            raise ValueError("现金流调节证据不属于同一案例。")

    point_by_year = {int(point["period_year"]): point for point in points}
    if len(point_by_year) != len(points):
        raise ValueError("财务历史中存在重复年度。")
    try:
        current = point_by_year[first["period_year"]]
        comparison = point_by_year[first["comparison_year"]]
    except KeyError as error:
        raise ValueError("财务历史缺少异常案例的当期或对比期。") from error
    if current["company_code"] != first["company_code"]:
        raise ValueError("财务历史与异常证据的公司不一致。")

    revenue_growth = _growth(current["revenue"], comparison["revenue"])
    net_profit_growth = _growth(
        current["net_profit"],
        comparison["net_profit"],
    )
    cash_flow_growth = _growth(
        current["operating_cash_flow"],
        comparison["operating_cash_flow"],
    )
    signal_detected = (
        revenue_growth > 0
        and net_profit_growth > 0
        and cash_flow_growth < 0
    )

    current_total = sum(item["current_value"] for item in components)
    comparison_total = sum(
        item["comparison_value"] for item in components
    )
    current_cash_flow = float(current["operating_cash_flow"])
    comparison_cash_flow = float(comparison["operating_cash_flow"])
    if not _close(current_total, current_cash_flow) or not _close(
        comparison_total,
        comparison_cash_flow,
    ):
        raise ValueError("现金流调节表与已核验经营现金流不勾稽。")

    ranked = sorted(
        components,
        key=lambda item: abs(
            item["current_value"] - item["comparison_value"]
        ),
        reverse=True,
    )
    drivers: list[CashFlowBridgeDriver] = []
    for rank, item in enumerate(ranked, start=1):
        contribution = item["current_value"] - item["comparison_value"]
        direction: Literal["拉低", "支撑", "不变"]
        if contribution < 0:
            direction = "拉低"
        elif contribution > 0:
            direction = "支撑"
        else:
            direction = "不变"
        drivers.append(
            {
                "rank": rank,
                "component_code": item["component_code"],
                "component_label": item["component_label"],
                "current_value": item["current_value"],
                "comparison_value": item["comparison_value"],
                "change_contribution": contribution,
                "absolute_change_contribution": abs(contribution),
                "direction": direction,
            }
        )

    bridge_change = current_total - comparison_total
    cash_flow_change = current_cash_flow - comparison_cash_flow
    if not _close(bridge_change, cash_flow_change):
        raise ValueError("调节项同比变化无法解释经营现金流变化。")

    largest_negative = next(
        (driver for driver in drivers if driver["change_contribution"] < 0),
        None,
    )
    positive_offsets = [
        driver for driver in drivers if driver["change_contribution"] > 0
    ][:3]
    confirmed_findings = [
        (
            f"{first['period_year']} 年营业收入同比 "
            f"{_format_percent(revenue_growth)}，归母净利润同比 "
            f"{_format_percent(net_profit_growth)}，但经营现金流净额同比 "
            f"{_format_percent(cash_flow_growth)}。"
        ),
        (
            "年报现金流量表补充资料逐项加总后，"
            f"分别等于 {_format_100m(current_cash_flow)} 和 "
            f"{_format_100m(comparison_cash_flow)}，勾稽通过。"
        ),
    ]
    if largest_negative is not None:
        confirmed_findings.append(
            f"最大的负向桥接项是“{largest_negative['component_label']}”："
            f"其对经营现金流的调节贡献由 "
            f"{_format_100m(largest_negative['comparison_value'])} 变为 "
            f"{_format_100m(largest_negative['current_value'])}，"
            f"同比少贡献 {_format_100m(abs(largest_negative['change_contribution']))}。"
        )
    if positive_offsets:
        offset_text = "、".join(
            f"{item['component_label']} {_format_100m(item['change_contribution'])}"
            for item in positive_offsets
        )
        confirmed_findings.append(
            f"主要正向抵消项为：{offset_text}。"
        )

    return {
        "company_code": first["company_code"],
        "company_name": first["company_name"],
        "canonical_code": first["canonical_code"],
        "period_year": first["period_year"],
        "comparison_year": first["comparison_year"],
        "revenue_growth": revenue_growth,
        "attributable_net_profit_growth": net_profit_growth,
        "operating_cash_flow_growth": cash_flow_growth,
        "signal_detected": signal_detected,
        "signal_label": (
            "收入与归母净利润增长，经营现金流下降"
            if signal_detected
            else "未触发本案例的方向背离规则"
        ),
        "operating_cash_flow_current": current_cash_flow,
        "operating_cash_flow_comparison": comparison_cash_flow,
        "operating_cash_flow_change": cash_flow_change,
        "bridge_current_total": current_total,
        "bridge_comparison_total": comparison_total,
        "bridge_change_total": bridge_change,
        "reconciliation_passed": True,
        "drivers": drivers,
        "confirmed_findings": confirmed_findings,
        "unresolved_questions": _build_unresolved_questions(drivers),
        "report_title": first["report_title"],
        "source_url": first["source_url"],
        "source_page": first["source_page"],
        "evidence_grade": first["evidence_grade"],
        "verification_status": first["verification_status"],
        "limitation": (
            "桥接项证明各调节项如何共同形成经营现金流变化，"
            "但不自动证明背后的业务因果。调节表起点是合并净利润，"
            "与趋势信号使用的归母净利润口径不同。"
            "本结果不预测未来业绩，不构成投资建议。"
        ),
    }
