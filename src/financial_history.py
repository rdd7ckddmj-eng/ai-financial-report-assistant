"""Verified point-in-time financial history for supported A-share cases.

The data file stores publication vintages rather than one timeless value.
When a later annual report restates an earlier year, the historical view uses
the original figure before the restatement date and the revised figure after
that date. This prevents future accounting information from leaking into an
earlier research snapshot.
"""

from __future__ import annotations

import csv
import math
import re
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Literal, TypedDict
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOUTAI_FINANCIAL_HISTORY_PATH = (
    PROJECT_ROOT / "data" / "verified" / "moutai_financial_history.csv"
)
CATL_FINANCIAL_HISTORY_PATH = (
    PROJECT_ROOT / "data" / "verified" / "catl_financial_history.csv"
)
FINANCIAL_HISTORY_CATALOG_PATH = (
    PROJECT_ROOT / "data" / "verified" / "financial_history_catalog.csv"
)
ALLOWED_REPORT_HOSTS = {
    "disc.static.szse.cn",
    "static.cninfo.com.cn",
    "dataclouds.cninfo.com.cn",
    "www.sse.com.cn",
    "static.sse.com.cn",
}
ACCOUNTING_BASES = {"original", "restated", "reported"}
EXCHANGE_NAMES = {
    "SH": "上海证券交易所",
    "SZ": "深圳证券交易所",
    "BJ": "北京证券交易所",
}
HISTORY_REQUIRED_FIELDS = {
    "company_code",
    "company_name",
    "period_year",
    "report_year",
    "published_date",
    "report_title",
    "source_url",
    "revenue",
    "net_profit",
    "operating_cash_flow",
    "total_assets",
    "total_liabilities",
    "summary_page",
    "balance_sheet_page",
    "evidence_grade",
    "verification_status",
    "accounting_basis",
    "notes",
}
CATALOG_REQUIRED_FIELDS = {
    "company_code",
    "company_name",
    "exchange",
    "exchange_name",
    "canonical_code",
    "data_file",
    "coverage_start_year",
    "coverage_end_year",
    "verified_periods",
    "reviewed_on",
    "status",
}


class FinancialHistoryRecord(TypedDict):
    """One audited annual fact set from one publication vintage."""

    company_code: str
    company_name: str
    period_year: int
    report_year: int
    published_date: date
    report_title: str
    source_url: str
    revenue: float
    net_profit: float
    operating_cash_flow: float
    total_assets: float
    total_liabilities: float
    summary_page: int
    balance_sheet_page: int
    evidence_grade: str
    verification_status: str
    accounting_basis: Literal["original", "restated", "reported"]
    notes: str


class FinancialTrendPoint(FinancialHistoryRecord):
    """One selected vintage with deterministic year-on-year calculations."""

    revenue_growth: float | None
    net_profit_growth: float | None
    operating_cash_flow_growth: float | None
    net_margin: float
    net_margin_change: float | None
    cash_conversion: float
    cash_conversion_change: float | None
    liabilities_to_assets: float
    liabilities_to_assets_change: float | None


class FinancialHistoryResult(TypedDict):
    """Point-in-time financial series plus an auditable publication filter."""

    as_of_date: str
    points: list[FinancialTrendPoint]
    available_vintage_count: int
    future_vintage_count: int
    restatement_count: int


class FinancialHistoryCase(TypedDict):
    """One approved company entry in the audited-history catalogue."""

    company_code: str
    company_name: str
    exchange: Literal["SH", "SZ", "BJ"]
    exchange_name: str
    canonical_code: str
    data_file: str
    coverage_start_year: int
    coverage_end_year: int
    verified_periods: int
    reviewed_on: date
    status: Literal["verified"]


class FinancialHistoryCatalogAudit(TypedDict):
    """Compact proof that every catalogue entry passed the same checks."""

    company_count: int
    financial_period_count: int
    publication_vintage_count: int
    all_checks_passed: bool
    cases: list[FinancialHistoryCase]


def _as_date(value: date | datetime | str, field_name: str) -> date:
    """Parse supported date values without accepting malformed input."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError as error:
        raise ValueError(f"{field_name} 不是有效的 ISO 日期。") from error


def _positive_float(value: str, field_name: str) -> float:
    """Parse one positive audited amount."""
    try:
        parsed = float(str(value).strip())
    except ValueError as error:
        raise ValueError(f"{field_name} 不是有效数字。") from error
    if not math.isfinite(parsed) or parsed <= 0:
        raise ValueError(f"{field_name} 必须是大于零的有限数字。")
    return parsed


def _positive_int(value: str, field_name: str) -> int:
    """Parse one positive page or year field."""
    try:
        parsed = int(str(value).strip())
    except ValueError as error:
        raise ValueError(f"{field_name} 不是有效整数。") from error
    if parsed <= 0:
        raise ValueError(f"{field_name} 必须大于零。")
    return parsed


def _expected_exchange(company_code: str) -> str:
    """Infer the A-share exchange so catalogue identities cannot disagree."""
    if not re.fullmatch(r"\d{6}", company_code):
        raise ValueError("接入目录中的股票代码必须是6位数字。")
    if company_code.startswith(("600", "601", "603", "605", "688", "689")):
        return "SH"
    if company_code.startswith(("000", "001", "002", "003", "300", "301")):
        return "SZ"
    if company_code.startswith(("4", "8", "920")):
        return "BJ"
    raise ValueError("接入目录中的股票代码无法匹配沪、深或北交所。")


def _validate_catalog_row(row: dict[str, str]) -> FinancialHistoryCase:
    """Validate one onboarding row before its financial file is accepted."""
    company_code = str(row["company_code"]).strip()
    company_name = str(row["company_name"]).strip()
    exchange = str(row["exchange"]).strip().upper()
    exchange_name = str(row["exchange_name"]).strip()
    canonical_code = str(row["canonical_code"]).strip().upper()
    data_file = str(row["data_file"]).strip()
    status = str(row["status"]).strip()

    if not company_name:
        raise ValueError("接入目录中的公司名称不能为空。")
    expected_exchange = _expected_exchange(company_code)
    if exchange != expected_exchange:
        raise ValueError("接入目录中的交易所与股票代码不一致。")
    if exchange_name != EXCHANGE_NAMES[exchange]:
        raise ValueError("接入目录中的交易所名称不一致。")
    if canonical_code != f"{company_code}.{exchange}":
        raise ValueError("接入目录中的标准股票代码不一致。")
    if (
        not data_file
        or Path(data_file).name != data_file
        or Path(data_file).suffix.lower() != ".csv"
        or data_file == FINANCIAL_HISTORY_CATALOG_PATH.name
    ):
        raise ValueError("接入目录只能引用同目录下的独立 CSV 数据文件。")
    if status != "verified":
        raise ValueError("只有 verified 公司可以进入多年财务趋势目录。")

    start_year = _positive_int(
        row["coverage_start_year"],
        "coverage_start_year",
    )
    end_year = _positive_int(
        row["coverage_end_year"],
        "coverage_end_year",
    )
    verified_periods = _positive_int(
        row["verified_periods"],
        "verified_periods",
    )
    if start_year > end_year:
        raise ValueError("核验覆盖的开始年度不能晚于结束年度。")
    if verified_periods != end_year - start_year + 1:
        raise ValueError("核验年度数量必须与连续覆盖区间一致。")
    reviewed_on = _as_date(row["reviewed_on"], "reviewed_on")
    if reviewed_on > date.today():
        raise ValueError("接入目录的复核日期不能晚于今天。")

    return {
        "company_code": company_code,
        "company_name": company_name,
        "exchange": exchange,
        "exchange_name": exchange_name,
        "canonical_code": canonical_code,
        "data_file": data_file,
        "coverage_start_year": start_year,
        "coverage_end_year": end_year,
        "verified_periods": verified_periods,
        "reviewed_on": reviewed_on,
        "status": "verified",
    }


def _validate_record(
    row: dict[str, str],
    expected_company_code: str,
) -> FinancialHistoryRecord:
    """Validate identity, source provenance, pages, and accounting values."""
    if row["company_code"] != expected_company_code:
        raise ValueError("财务基准中的股票代码与所选公司不一致。")
    if not str(row["company_name"]).strip():
        raise ValueError("财务基准中的公司名称不能为空。")
    if not str(row["report_title"]).strip():
        raise ValueError("财务基准中的年度报告名称不能为空。")

    source_url = str(row["source_url"]).strip()
    parsed_url = urlparse(source_url)
    if (
        parsed_url.scheme != "https"
        or parsed_url.hostname not in ALLOWED_REPORT_HOSTS
    ):
        raise ValueError("财务基准必须使用允许的官方 HTTPS 来源。")

    if row["evidence_grade"] != "A":
        raise ValueError("财务基准必须保留 A 级证据。")
    if row["verification_status"] != "verified":
        raise ValueError("未核验财务数据不能进入多年趋势案例。")
    if row["accounting_basis"] not in ACCOUNTING_BASES:
        raise ValueError("财务基准的会计口径标记无效。")

    period_year = _positive_int(row["period_year"], "period_year")
    report_year = _positive_int(row["report_year"], "report_year")
    if period_year > report_year:
        raise ValueError("财务期间不能晚于报告年度。")

    total_assets = _positive_float(row["total_assets"], "total_assets")
    total_liabilities = _positive_float(
        row["total_liabilities"],
        "total_liabilities",
    )
    if total_liabilities > total_assets:
        raise ValueError("总负债不能大于总资产。")

    published_date = _as_date(
        row["published_date"],
        "published_date",
    )
    if published_date.year <= report_year:
        raise ValueError("A股年度报告公开日期必须晚于报告年度。")

    return {
        "company_code": row["company_code"],
        "company_name": row["company_name"],
        "period_year": period_year,
        "report_year": report_year,
        "published_date": published_date,
        "report_title": row["report_title"].strip(),
        "source_url": source_url,
        "revenue": _positive_float(row["revenue"], "revenue"),
        "net_profit": _positive_float(row["net_profit"], "net_profit"),
        "operating_cash_flow": _positive_float(
            row["operating_cash_flow"],
            "operating_cash_flow",
        ),
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "summary_page": _positive_int(
            row["summary_page"],
            "summary_page",
        ),
        "balance_sheet_page": _positive_int(
            row["balance_sheet_page"],
            "balance_sheet_page",
        ),
        "evidence_grade": row["evidence_grade"],
        "verification_status": row["verification_status"],
        "accounting_basis": row["accounting_basis"],
        "notes": row["notes"].strip(),
    }


def _read_financial_history_catalog(
    path: Path = FINANCIAL_HISTORY_CATALOG_PATH,
) -> list[FinancialHistoryCase]:
    """Read and structurally validate the source-controlled onboarding list."""
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            missing = CATALOG_REQUIRED_FIELDS - set(reader.fieldnames or [])
            if missing:
                raise ValueError(
                    "接入目录缺少字段：" + "、".join(sorted(missing))
                )
            rows = list(reader)
    except OSError as error:
        raise ValueError("无法读取多年财务趋势接入目录。") from error

    if not rows:
        raise ValueError("多年财务趋势接入目录为空。")
    cases = [_validate_catalog_row(row) for row in rows]
    identity_sets = (
        ("股票代码", [case["company_code"] for case in cases]),
        ("标准股票代码", [case["canonical_code"] for case in cases]),
        ("数据文件", [case["data_file"] for case in cases]),
    )
    for label, values in identity_sets:
        if len(values) != len(set(values)):
            raise ValueError(f"接入目录存在重复{label}。")
    return cases


def _load_financial_history_file(
    expected_company_code: str,
    data_path: Path,
) -> list[FinancialHistoryRecord]:
    """Load and validate one company's publication vintages."""
    try:
        with data_path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            missing = HISTORY_REQUIRED_FIELDS - set(reader.fieldnames or [])
            if missing:
                raise ValueError(
                    "财务基准缺少字段：" + "、".join(sorted(missing))
                )
            rows = list(reader)
    except OSError as error:
        raise ValueError("无法读取该公司的多年财务基准。") from error

    if not rows:
        raise ValueError("该公司的多年财务基准为空。")
    records = [
        _validate_record(row, expected_company_code) for row in rows
    ]
    if len({record["company_name"] for record in records}) != 1:
        raise ValueError("同一财务基准中出现了多个公司名称。")
    identities = [
        (
            record["period_year"],
            record["report_year"],
            record["published_date"],
        )
        for record in records
    ]
    if len(identities) != len(set(identities)):
        raise ValueError("该公司的多年财务基准存在重复版本。")
    return sorted(
        records,
        key=lambda record: (
            record["published_date"],
            record["period_year"],
        ),
    )


def load_financial_history_catalog(
    path: Path = FINANCIAL_HISTORY_CATALOG_PATH,
) -> list[FinancialHistoryCase]:
    """Accept only catalogue entries whose linked data passes every check."""
    cases = _read_financial_history_catalog(path)
    for case in cases:
        try:
            records = _load_financial_history_file(
                case["company_code"],
                path.parent / case["data_file"],
            )
        except ValueError as error:
            raise ValueError(
                f"{case['company_name']}接入校验失败：{error}"
            ) from error
        if {record["company_name"] for record in records} != {
            case["company_name"]
        }:
            raise ValueError("接入目录中的公司名称与财务数据不一致。")
        actual_periods = sorted({record["period_year"] for record in records})
        expected_periods = list(
            range(
                case["coverage_start_year"],
                case["coverage_end_year"] + 1,
            )
        )
        if actual_periods != expected_periods:
            raise ValueError(
                f"{case['company_name']}的财务年度与接入目录不一致。"
            )
    return cases


def audit_financial_history_catalog(
    path: Path = FINANCIAL_HISTORY_CATALOG_PATH,
) -> FinancialHistoryCatalogAudit:
    """Summarise the common onboarding checks for product display and CI."""
    cases = load_financial_history_catalog(path)
    publication_vintage_count = sum(
        len(
            _load_financial_history_file(
                case["company_code"],
                path.parent / case["data_file"],
            )
        )
        for case in cases
    )
    return {
        "company_count": len(cases),
        "financial_period_count": sum(
            case["verified_periods"] for case in cases
        ),
        "publication_vintage_count": publication_vintage_count,
        "all_checks_passed": True,
        "cases": cases,
    }


def verified_financial_history_codes() -> tuple[str, ...]:
    """Return companies whose catalogue rows and data files both validate."""
    return tuple(
        case["company_code"] for case in load_financial_history_catalog()
    )


def load_verified_financial_history(
    company_code: str,
    path: Path | None = None,
) -> list[FinancialHistoryRecord]:
    """Load one company's manually checked, source-controlled vintages."""
    expected_company_code = str(company_code).strip()
    if path is None:
        cases = _read_financial_history_catalog()
        matched = next(
            (
                case
                for case in cases
                if case["company_code"] == expected_company_code
            ),
            None,
        )
        if matched is None:
            raise ValueError("该公司尚未建立已核验的多年财务基准。")
        data_path = FINANCIAL_HISTORY_CATALOG_PATH.parent / matched["data_file"]
    else:
        data_path = path
    return _load_financial_history_file(expected_company_code, data_path)


def load_moutai_financial_history(
    path: Path = MOUTAI_FINANCIAL_HISTORY_PATH,
) -> list[FinancialHistoryRecord]:
    """Keep the original flagship loader as a stable public interface."""
    return load_verified_financial_history("600519", path)


def _growth(current: float, previous: float | None) -> float | None:
    """Calculate a transparent year-on-year rate when a base exists."""
    if previous is None or previous == 0:
        return None
    return current / previous - 1


def _difference(current: float, previous: float | None) -> float | None:
    """Return a simple ratio change without calling it a growth rate."""
    if previous is None:
        return None
    return current - previous


def select_financial_history_as_of(
    records: Iterable[FinancialHistoryRecord],
    as_of_date: date | str,
) -> FinancialHistoryResult:
    """Select the latest known vintage for each year at the historical cut-off."""
    cutoff = _as_date(as_of_date, "历史截止日")
    available: list[FinancialHistoryRecord] = []
    future: list[FinancialHistoryRecord] = []
    for record in records:
        if record["published_date"] <= cutoff:
            available.append(record)
        else:
            future.append(record)

    latest_by_period: dict[int, FinancialHistoryRecord] = {}
    for record in sorted(
        available,
        key=lambda item: (
            item["published_date"],
            item["report_year"],
        ),
    ):
        latest_by_period[record["period_year"]] = record

    selected = [
        latest_by_period[year] for year in sorted(latest_by_period)
    ]
    points: list[FinancialTrendPoint] = []
    previous: FinancialHistoryRecord | None = None
    for record in selected:
        net_margin = record["net_profit"] / record["revenue"]
        cash_conversion = (
            record["operating_cash_flow"] / record["net_profit"]
        )
        liabilities_to_assets = (
            record["total_liabilities"] / record["total_assets"]
        )
        previous_net_margin = (
            previous["net_profit"] / previous["revenue"]
            if previous
            else None
        )
        previous_cash_conversion = (
            previous["operating_cash_flow"] / previous["net_profit"]
            if previous
            else None
        )
        previous_liabilities_to_assets = (
            previous["total_liabilities"] / previous["total_assets"]
            if previous
            else None
        )
        points.append(
            {
                **record,
                "revenue_growth": _growth(
                    record["revenue"],
                    previous["revenue"] if previous else None,
                ),
                "net_profit_growth": _growth(
                    record["net_profit"],
                    previous["net_profit"] if previous else None,
                ),
                "operating_cash_flow_growth": _growth(
                    record["operating_cash_flow"],
                    previous["operating_cash_flow"] if previous else None,
                ),
                "net_margin": net_margin,
                "net_margin_change": _difference(
                    net_margin,
                    previous_net_margin,
                ),
                "cash_conversion": cash_conversion,
                "cash_conversion_change": _difference(
                    cash_conversion,
                    previous_cash_conversion,
                ),
                "liabilities_to_assets": liabilities_to_assets,
                "liabilities_to_assets_change": _difference(
                    liabilities_to_assets,
                    previous_liabilities_to_assets,
                ),
            }
        )
        previous = record

    return {
        "as_of_date": cutoff.isoformat(),
        "points": points,
        "available_vintage_count": len(available),
        "future_vintage_count": len(future),
        "restatement_count": sum(
            point["accounting_basis"] == "restated" for point in points
        ),
    }
