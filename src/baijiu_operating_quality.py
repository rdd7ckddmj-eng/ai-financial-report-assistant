"""Audited baijiu operating-quality metrics for verified peer comparisons.

The source file stores only the additional annual-report facts that are not in
the general financial-history catalogue.  Ratios are calculated here in Python
and remain descriptive: inventory is not automatically excess stock, contract
liabilities are not a sales forecast, and no combined quality score is built.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import TypedDict
from urllib.parse import urlparse

from src.cross_company_comparison import CrossCompanyComparisonRow


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BAIJIU_OPERATING_QUALITY_PATH = (
    PROJECT_ROOT / "data" / "verified" / "baijiu_operating_quality.csv"
)
ALLOWED_REPORT_HOSTS = {
    "disc.static.szse.cn",
    "static.cninfo.com.cn",
    "www.sse.com.cn",
}
EXPECTED_COMPANY_CODES = {"600519", "000858", "000568"}
REQUIRED_FIELDS = {
    "company_code",
    "company_name",
    "period_year",
    "published_date",
    "report_title",
    "source_url",
    "cost_of_sales",
    "inventory",
    "prior_year_inventory",
    "contract_liabilities",
    "prior_year_contract_liabilities",
    "income_statement_page",
    "inventory_page",
    "contract_liabilities_page",
    "evidence_grade",
    "verification_status",
    "notes",
}


class BaijiuOperatingQualityRecord(TypedDict):
    """One company's additional audited facts for one reporting year."""

    company_code: str
    company_name: str
    period_year: int
    published_date: str
    report_title: str
    source_url: str
    cost_of_sales: float
    inventory: float
    prior_year_inventory: float
    contract_liabilities: float
    prior_year_contract_liabilities: float
    income_statement_page: int
    inventory_page: int
    contract_liabilities_page: int
    evidence_grade: str
    verification_status: str
    notes: str


class BaijiuOperatingQualityRow(BaijiuOperatingQualityRecord):
    """Audited facts plus deterministic descriptive ratios."""

    revenue: float
    net_profit: float
    operating_cash_flow: float
    total_assets: float
    gross_margin: float
    inventory_to_assets: float
    inventory_growth: float
    contract_liabilities_to_revenue: float
    contract_liabilities_growth: float
    cash_conversion: float


class BaijiuOperatingQualityResult(TypedDict):
    """A peer-only panel with no composite ranking or forecast."""

    period_year: int
    company_count: int
    rows: list[BaijiuOperatingQualityRow]
    observations: list[str]
    limitation: str


def _positive_float(value: object, field_name: str) -> float:
    """Accept only positive finite audited amounts."""
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} 不是有效数字。") from error
    if not math.isfinite(parsed) or parsed <= 0:
        raise ValueError(f"{field_name} 必须是大于零的有限数字。")
    return parsed


def _positive_int(value: object, field_name: str) -> int:
    """Accept only positive report-page and reporting-year values."""
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} 不是有效整数。") from error
    if parsed <= 0:
        raise ValueError(f"{field_name} 必须大于零。")
    return parsed


def load_baijiu_operating_quality(
    path: Path = BAIJIU_OPERATING_QUALITY_PATH,
) -> list[BaijiuOperatingQualityRecord]:
    """Load and audit the small source-controlled baijiu dataset."""
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        missing_fields = REQUIRED_FIELDS.difference(reader.fieldnames or [])
        if missing_fields:
            raise ValueError(
                "白酒经营质量数据缺少字段："
                + "、".join(sorted(missing_fields))
            )
        raw_rows = list(reader)

    records: list[BaijiuOperatingQualityRecord] = []
    seen_keys: set[tuple[str, int]] = set()
    for raw in raw_rows:
        company_code = str(raw["company_code"]).strip()
        company_name = str(raw["company_name"]).strip()
        period_year = _positive_int(raw["period_year"], "period_year")
        published_date = str(raw["published_date"]).strip()
        report_title = str(raw["report_title"]).strip()
        source_url = str(raw["source_url"]).strip()
        evidence_grade = str(raw["evidence_grade"]).strip()
        verification_status = str(raw["verification_status"]).strip()
        notes = str(raw["notes"]).strip()

        if not company_name or not report_title or not notes:
            raise ValueError("公司名称、报告标题和口径说明不能为空。")
        try:
            disclosure_date = date.fromisoformat(published_date)
        except ValueError as error:
            raise ValueError("published_date 不是有效日期。") from error
        if disclosure_date > date.today():
            raise ValueError("白酒经营质量证据的公开日期不能晚于今天。")
        parsed_url = urlparse(source_url)
        if (
            parsed_url.scheme != "https"
            or parsed_url.hostname not in ALLOWED_REPORT_HOSTS
            or not parsed_url.path.lower().endswith(".pdf")
        ):
            raise ValueError("白酒经营质量证据必须来自允许的官方 PDF。")
        if evidence_grade != "A" or verification_status != "verified":
            raise ValueError("白酒经营质量数据必须是 A 级 verified 证据。")

        key = (company_code, period_year)
        if key in seen_keys:
            raise ValueError("白酒经营质量数据不能重复公司和年度。")
        seen_keys.add(key)
        records.append(
            {
                "company_code": company_code,
                "company_name": company_name,
                "period_year": period_year,
                "published_date": published_date,
                "report_title": report_title,
                "source_url": source_url,
                "cost_of_sales": _positive_float(
                    raw["cost_of_sales"], "cost_of_sales"
                ),
                "inventory": _positive_float(raw["inventory"], "inventory"),
                "prior_year_inventory": _positive_float(
                    raw["prior_year_inventory"], "prior_year_inventory"
                ),
                "contract_liabilities": _positive_float(
                    raw["contract_liabilities"], "contract_liabilities"
                ),
                "prior_year_contract_liabilities": _positive_float(
                    raw["prior_year_contract_liabilities"],
                    "prior_year_contract_liabilities",
                ),
                "income_statement_page": _positive_int(
                    raw["income_statement_page"], "income_statement_page"
                ),
                "inventory_page": _positive_int(
                    raw["inventory_page"], "inventory_page"
                ),
                "contract_liabilities_page": _positive_int(
                    raw["contract_liabilities_page"],
                    "contract_liabilities_page",
                ),
                "evidence_grade": evidence_grade,
                "verification_status": verification_status,
                "notes": notes,
            }
        )

    if {record["company_code"] for record in records} != EXPECTED_COMPANY_CODES:
        raise ValueError("白酒经营质量数据必须完整覆盖三家已核验公司。")
    if {record["period_year"] for record in records} != {2025}:
        raise ValueError("首版白酒经营质量数据只接受共同的 2025 年度。")
    return records


def build_baijiu_operating_quality(
    comparison_rows: Sequence[CrossCompanyComparisonRow],
    records: Sequence[BaijiuOperatingQualityRecord],
) -> BaijiuOperatingQualityResult:
    """Join general audited facts to baijiu-only evidence and calculate ratios."""
    selected_rows = list(comparison_rows)
    if len(selected_rows) < 2:
        raise ValueError("白酒经营质量透视至少需要两家公司。")
    years = {int(row["period_year"]) for row in selected_rows}
    if len(years) != 1:
        raise ValueError("白酒经营质量透视必须使用同一财务年度。")
    period_year = years.pop()
    record_by_key = {
        (record["company_code"], record["period_year"]): record
        for record in records
    }

    result_rows: list[BaijiuOperatingQualityRow] = []
    for comparison in selected_rows:
        key = (comparison["company_code"], period_year)
        record = record_by_key.get(key)
        if record is None:
            raise ValueError(
                f"{comparison['company_name']}缺少该年度白酒经营质量证据。"
            )
        if (
            record["company_name"] != comparison["company_name"]
            or record["published_date"] != comparison["published_date"]
            or record["report_title"] != comparison["report_title"]
            or record["source_url"] != comparison["source_url"]
        ):
            raise ValueError("白酒经营质量证据与通用财务记录不一致。")

        revenue = _positive_float(comparison["revenue"], "revenue")
        net_profit = _positive_float(comparison["net_profit"], "net_profit")
        operating_cash_flow = _positive_float(
            comparison["operating_cash_flow"], "operating_cash_flow"
        )
        total_assets = _positive_float(
            comparison["total_assets"], "total_assets"
        )
        if record["cost_of_sales"] >= revenue:
            raise ValueError("营业成本必须低于营业收入才能计算毛利率。")

        result_rows.append(
            {
                **record,
                "revenue": revenue,
                "net_profit": net_profit,
                "operating_cash_flow": operating_cash_flow,
                "total_assets": total_assets,
                "gross_margin": (revenue - record["cost_of_sales"]) / revenue,
                "inventory_to_assets": record["inventory"] / total_assets,
                "inventory_growth": (
                    record["inventory"] / record["prior_year_inventory"] - 1
                ),
                "contract_liabilities_to_revenue": (
                    record["contract_liabilities"] / revenue
                ),
                "contract_liabilities_growth": (
                    record["contract_liabilities"]
                    / record["prior_year_contract_liabilities"]
                    - 1
                ),
                "cash_conversion": operating_cash_flow / net_profit,
            }
        )

    gross_margin_low = min(result_rows, key=lambda item: item["gross_margin"])
    gross_margin_high = max(result_rows, key=lambda item: item["gross_margin"])
    inventory_growth_low = min(
        result_rows, key=lambda item: item["inventory_growth"]
    )
    inventory_growth_high = max(
        result_rows, key=lambda item: item["inventory_growth"]
    )
    contract_up = [
        item["company_name"]
        for item in result_rows
        if item["contract_liabilities_growth"] > 0
    ]
    contract_down = [
        item["company_name"]
        for item in result_rows
        if item["contract_liabilities_growth"] < 0
    ]

    observations = [
        (
            "合并口径毛利率区间两端为"
            f"{gross_margin_low['company_name']}与"
            f"{gross_margin_high['company_name']}；产品结构和收入确认口径"
            "不同，不能据此形成质量排名。"
        ),
        (
            "三家公司年末存货均同比增加，增幅区间为"
            f"{inventory_growth_low['inventory_growth']:.1%}—"
            f"{inventory_growth_high['inventory_growth']:.1%}；"
            "白酒存货包含需要长期储存的基酒，增加不等同于积压。"
        ),
        (
            "年末合同负债同比增加的公司为"
            f"{'、'.join(contract_up) or '无'}，同比减少的公司为"
            f"{'、'.join(contract_down) or '无'}；该余额是单一时点的"
            "客户预付款，不是未来收入预测。"
        ),
        (
            "经营现金/归母净利润保留为独立现金质量指标；显著高于或"
            "低于 1 倍时仍需结合收入确认、税费和营运资金变动核查。"
        ),
    ]
    limitation = (
        "本面板使用合并财务报表，不直接等同于旗舰白酒单品表现。"
        "存货占资产会受到财务公司和其他资产结构影响；合同负债是年末"
        "时点数，不能单独解释为订单或需求；五粮液 2025 年报另披露"
        "部分业务收入确认核算调整。页面不生成综合得分、盈利预测或"
        "买卖建议。"
    )
    return {
        "period_year": period_year,
        "company_count": len(result_rows),
        "rows": result_rows,
        "observations": observations,
        "limitation": limitation,
    }
