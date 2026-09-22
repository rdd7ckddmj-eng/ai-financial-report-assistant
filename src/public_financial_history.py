"""Bounded current-vintage annual financial coverage for ordinary A-share codes.

Public vendor rows are candidates, never the audited history catalogue. They
cannot reconstruct what was known at a historical date. All arithmetic below
uses the returned base amounts; missing values and negative growth bases are
not replaced by vendor percentages or values from another company.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import json
import math
from time import monotonic

from src.china_stock import DataSourceError, build_company_identity


API_URL = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
SOURCE_NAME = "东方财富年度财务公开数据（待核验）"
MAX_ANNUAL_PERIODS = 6
MAX_RESPONSE_BYTES = 512_000
SCHEMA = "public-financial-history.v1"
LIMITATION = (
    "公开源当前版本，未经官方年报逐页核验；不代表历史时点可知数据，"
    "不得用于 Historical Lens。同比按相邻完整年度的当前版本计算，"
    "重述或口径变化仍需查阅年报；数据缺失不等于零。"
)
# Keep revenue and total operating revenue separate (e.g. Gree has both).
AMOUNT_FIELDS = {
    "revenue": ("OPERATE_INCOME_PK", "营业收入"),
    "total_operating_revenue": ("TOTALOPERATEREVE", "营业总收入"),
    "net_profit": ("PARENTNETPROFIT", "归母净利润"),
    "operating_cash_flow": ("NETCASH_OPERATE_PK", "经营现金流量净额"),
    "total_assets": ("TOTAL_ASSETS_PK", "总资产"),
    "total_liabilities": ("LIABILITY", "总负债"),
    "total_equity": ("TOTAL_EQUITY_PK", "所有者权益合计"),
}
SECTOR_FIELDS = {
    "银行": {
        "NEWCAPITALADER": "资本充足率",
        "HXYJBCZL": "核心一级资本充足率",
        "NONPERLOAN": "不良贷款率",
        "BLDKBBL": "拨备覆盖率",
        "NET_INTEREST_MARGIN": "净息差",
    },
    "保险": {"SOLVENCY_AR": "偿付能力充足率"},
    "证券": {"RISK_COVERAGE": "风险覆盖率", "CAPITAL_LEVERAGE_RATIO": "资本杠杆率"},
}
_META_FIELDS = (
    "SECUCODE", "SECURITY_CODE", "SECURITY_NAME_ABBR", "ORG_TYPE",
    "REPORT_DATE", "REPORT_TYPE", "NOTICE_DATE", "UPDATE_DATE", "CURRENCY",
)


def _number(value: object, field: str) -> float | None:
    if value is None or value in ("", "--", "-", "null"):
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field}不是有效金额。")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field}不是有效金额，不能猜测单位。") from exc
    if not math.isfinite(result):
        raise ValueError(f"{field}必须是有限数字。")
    return result


def _date(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"缺少{field}。")
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field}格式错误。") from exc
    return parsed.date().isoformat()


def _stamp(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("取数时间必须是带时区的日期时间文本。")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("取数时间必须包含时区。")
    return parsed.astimezone(timezone.utc)


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    value = numerator / denominator
    return value if math.isfinite(value) else None


def build_public_financial_history(
    company: Mapping[str, object], rows: Sequence[Mapping[str, object]], *, fetched_at: str,
) -> dict:
    """Validate identity, annual periods, currency and vintages; retain gaps."""
    observed = _stamp(fetched_at)
    expected = build_company_identity(str(company["code"]), str(company["name"]))
    if company.get("canonical_code") != expected["canonical_code"]:
        raise ValueError("公司代码与交易所不一致。")
    if not isinstance(rows, (list, tuple)) or len(rows) > MAX_ANNUAL_PERIODS:
        raise ValueError("公开财务请求最多接受六个年度。")
    if not rows:
        raise ValueError("公开源没有返回该公司的年度财务数据。")
    compact_rows, points, issues = [], [], []
    seen = set()
    org_types = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("财务数据行不是对象。")
        if row.get("SECUCODE") != expected["canonical_code"] or row.get("SECURITY_CODE") != expected["code"]:
            raise ValueError("公开财务数据与请求公司不匹配。")
        name = row.get("SECURITY_NAME_ABBR")
        org_type = row.get("ORG_TYPE")
        if not isinstance(name, str) or not name.strip() or len(name) > 120:
            raise ValueError("公开财务数据缺少有效公司名称。")
        if not isinstance(org_type, str) or not org_type or len(org_type) > 30:
            raise ValueError("公开财务数据缺少机构类型。")
        if row.get("CURRENCY") != "CNY":
            raise ValueError("该数据不是人民币口径，不能并入人民币趋势。")
        period = _date(row.get("REPORT_DATE"), "报告期")
        if not period.endswith("12-31") or row.get("REPORT_TYPE") != "年报":
            raise ValueError("只接受完整年度，不能把季度或中报混入年度趋势。")
        published = _date(row.get("NOTICE_DATE"), "公告日期")
        updated = _date(row.get("UPDATE_DATE"), "版本更新日期")
        if published < period or updated < published or max(published, updated) > observed.date().isoformat():
            raise ValueError("财务报告日期或版本日期超出本次取数时点。")
        if period in seen:
            raise ValueError("同一年度出现重复或冲突版本，需要先核验。")
        seen.add(period)
        org_types.add(org_type)
        clean = {key: row.get(key) for key in _META_FIELDS}
        clean.update(REPORT_DATE=period, NOTICE_DATE=published, UPDATE_DATE=updated)
        point = {"period_year": int(period[:4]), "report_date": period,
                 "published_date": published, "updated_date": updated, "org_type": org_type}
        missing = []
        for key, (field, label) in AMOUNT_FIELDS.items():
            number = _number(row.get(field), field)
            if key in {"revenue", "total_operating_revenue", "total_assets", "total_liabilities"} and number is not None and number < 0:
                raise ValueError(f"{label}出现负值，需要核验原始口径。")
            point[key] = clean[field] = number
            if number is None:
                missing.append(label)
        point["missing_fields"] = missing
        sector_metrics = {}
        for field, label in SECTOR_FIELDS.get(org_type, {}).items():
            clean[field] = _number(row.get(field), field)
            sector_metrics[label] = clean[field]  # Provider-reported %, not independently computed.
        point["sector_metrics_percent"] = sector_metrics
        assets, liabilities, equity = (point[key] for key in ("total_assets", "total_liabilities", "total_equity"))
        point["balance_check"] = "unavailable"
        if all(value is not None for value in (assets, liabilities, equity)):
            point["balance_check"] = "passed" if math.isclose(assets, liabilities + equity, rel_tol=1e-5, abs_tol=1.0) else "failed"
            if point["balance_check"] == "failed":
                issues.append(f"{period[:4]}年资产不等于负债加权益；暂停该期负债率计算，需核对来源。")
        if missing:
            issues.append(f"{period[:4]}年缺少：{'、'.join(missing)}。")
        point["liabilities_to_assets"] = _ratio(liabilities, assets) if point["balance_check"] != "failed" else None
        point["parent_profit_margin"] = _ratio(point["net_profit"], point["revenue"]) if org_type == "通用" else None
        point["cash_to_parent_profit"] = _ratio(point["operating_cash_flow"], point["net_profit"]) if org_type == "通用" else None
        points.append(point)
        compact_rows.append(clean)
    if len(org_types) > 1:
        issues.append("跨年机构类型变化，仅展示数据；不计算跨口径增长率。")
    points.sort(key=lambda p: p["period_year"])
    compact_rows.sort(key=lambda r: r["REPORT_DATE"])
    for index, point in enumerate(points):
        previous = points[index - 1] if index else None
        comparable = previous is not None and point["period_year"] == previous["period_year"] + 1 and point["org_type"] == previous["org_type"]
        for key in ("revenue", "net_profit", "operating_cash_flow"):
            base = previous[key] if comparable else None
            change = point[key] - base if point[key] is not None and base is not None else None
            if change is not None and not math.isfinite(change):
                raise ValueError("跨年金额变化溢出，需核对原始金额。")
            point[key + "_change"] = change
            ratio = _ratio(point[key], base) if comparable else None
            point[key + "_growth"] = ratio - 1 if ratio is not None else None
        if previous and not comparable:
            issues.append(f"{point['period_year']}年缺少连续同口径比较期，不计算同比。")
    latest = points[-1]
    observations = []
    if latest["org_type"] == "通用":
        issues.append("源机构类型为通用报表模板，不代表已核实所属行业；金融控股等公司仍需人工判断规则适用性。")
        profit, cash = latest["net_profit_change"], latest["operating_cash_flow_change"]
        if profit is None or cash is None:
            observations.append("缺少连续年度的利润或经营现金流，无法判断两者是否背离。")
        elif profit > 0 and cash < 0:
            observations.append("归母净利润增加、经营现金流减少：属于方向背离候选，原因需查现金流附注，不能直接推断回款恶化。")
        else:
            observations.append("现有可比数字未触发利润增加、经营现金流减少规则；不代表没有其他风险。")
    else:
        issues.append("金融行业指标为源披露值，可能采用母公司或监管口径，不能等同于合并报表口径或直接跨公司比较。")
        observations.append(f"机构类型为{latest['org_type']}，不适用普通企业现金转化异常规则；展示适用的原始金额与行业指标。")
    if latest["period_year"] < observed.year - 1:
        issues.append(f"最新可用年度为{latest['period_year']}，资料可能滞后；不将旧数据标作最新财报。")
    basis = {
        "schema": SCHEMA, "company": expected,
        "fetched_at": observed.isoformat(timespec="seconds"),
        "source_rows": compact_rows,
    }
    fingerprint = sha256(json.dumps(basis, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    return {
        **basis, "status": "public_unverified", "source": SOURCE_NAME,
        "source_url": f"https://emweb.securities.eastmoney.com/pc_hsf10/pages/index.html?type=web&code={expected['exchange']}{expected['code']}#/cwfx",
        "fingerprint": fingerprint, "points": points, "issues": issues,
        "observations": observations, "limitation": LIMITATION,
        "amount_unit": "CNY元", "accounting_basis": "公开源合并数据候选；净利润为归母口径，需年报核验",
    }


def validate_public_financial_history(value: object) -> dict:
    """Rebuild from bounded source fields so imported calculations cannot lie."""
    if not isinstance(value, Mapping) or value.get("schema") != SCHEMA:
        raise ValueError("公开财务结果格式不受支持。")
    rebuilt = build_public_financial_history(value["company"], value["source_rows"], fetched_at=value["fetched_at"])
    if rebuilt != dict(value):
        raise ValueError("公开财务结果与来源字段、计算或核验状态不一致。")
    return rebuilt


def fetch_public_financial_history(company: Mapping[str, object]) -> dict:
    """One bounded request, no eager universe download and no shared PDF cache."""
    import requests

    canonical = build_company_identity(str(company["code"]))["canonical_code"]
    if canonical != company.get("canonical_code"):
        raise ValueError("公司代码与交易所不一致。")
    params = {
        "reportName": "RPT_F10_FINANCE_MAINFINADATA", "columns": "ALL",
        "filter": f'(SECUCODE="{canonical}")(REPORT_TYPE="年报")',
        "pageNumber": 1, "pageSize": MAX_ANNUAL_PERIODS,
        "sortTypes": -1, "sortColumns": "REPORT_DATE", "source": "HSF10", "client": "PC",
    }
    try:
        started = monotonic()
        with requests.get(API_URL, params=params, timeout=(5, 15), stream=True,
                          allow_redirects=False) as response:
            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError("公开财务源返回了非成功响应。")
            chunks, size = [], 0
            for chunk in response.iter_content(chunk_size=16_384):
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES or monotonic() - started > 25:
                    raise ValueError("公开财务响应超过安全大小或时间边界。")
                chunks.append(chunk)
            data = json.loads(b"".join(chunks))
        if not isinstance(data, dict) or data.get("success") is not True:
            raise ValueError("公开财务源本次未成功返回数据。")
        result = data.get("result")
        if not isinstance(result, dict):
            raise ValueError("公开财务源没有该公司数据。")
        return build_public_financial_history(company, result.get("data"), fetched_at=datetime.now(timezone.utc).isoformat())
    except (requests.RequestException, ValueError, TypeError, KeyError) as error:
        raise DataSourceError(f"年度公开财务数据未完成核验：{error}") from error


def compare_public_financial_histories(histories: Sequence[Mapping], year: int | None = None) -> dict:
    """Compare 2–5 explicitly selected companies without inventing a peer group."""
    if not 2 <= len(histories) <= 5:
        raise ValueError("横向比较需要2至5家公司。")
    items = [validate_public_financial_history(value) for value in histories]
    codes = [item["company"]["canonical_code"] for item in items]
    if len(set(codes)) != len(codes):
        raise ValueError("不能重复选择同一家公司。")
    common = set.intersection(*({p["period_year"] for p in item["points"]} for item in items))
    if not common:
        raise ValueError("没有共同财务年度，不能强行对比。")
    year = max(common) if year is None else year
    if year not in common:
        raise ValueError("选择的年度不在所有公司的共同覆盖中。")
    rows = [{"company": item["company"], "source_url": item["source_url"],
             "fetched_at": item["fetched_at"], **next(p for p in item["points"] if p["period_year"] == year)} for item in items]
    return {"year": year, "common_years": sorted(common), "rows": rows,
            "limitation": "共同年度公开源比较，未经逐页核验；同属通用报表不代表同业。不同金融机构类型只比较原始规模，不排名、不计算综合评分。"}


def render_public_financial_report(history: Mapping) -> str:
    history = validate_public_financial_history(history)
    e = lambda value: escape(str(value), quote=True)
    def amount(value):
        return "缺失" if value is None else f"{value:,.2f}"
    headers = ["年度", *(label for _, label in AMOUNT_FIELDS.values()), "公告日", "更新日", "资产勾稽"]
    rows = "".join("<tr>" + "".join(f"<td>{e(v)}</td>" for v in [p["period_year"], *(amount(p[k]) for k in AMOUNT_FIELDS), p["published_date"], p["updated_date"], p["balance_check"]]) + "</tr>" for p in history["points"])
    notes = "".join(f"<li>{e(note)}</li>" for note in [*history["observations"], *history["issues"]])
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>年度公开财务研究</title>
<style>body{{font:16px system-ui;margin:36px;color:#172536}}table{{border-collapse:collapse;font-size:13px}}td,th{{border:1px solid #ccc;padding:8px}}.notice{{background:#fff3cd;padding:16px}}</style>
<h1>{e(history['company']['name'])} · 年度公开财务研究</h1><p>{e(history['company']['canonical_code'])}｜人民币元｜取数：{e(history['fetched_at'])}</p>
<p class="notice">待核验研究资料，不是已核验正式底稿。{e(history['limitation'])}</p>
<p><a href="{e(history['source_url'])}">查看公开数据来源（非官方年报）</a></p>
<table><thead><tr>{''.join(f'<th>{e(h)}</th>' for h in headers)}</tr></thead><tbody>{rows}</tbody></table>
<h2>观察与缺口</h2><ul>{notes}</ul><h2>计算口径</h2>
<p>同比＝本期÷相邻年度基期－1，仅在基期大于0时计算；归母净利润÷营业收入不等于合并净利率。经营现金流÷归母净利润存在口径差异，仅为普通企业描述指标。资产勾稽通过不代表已审计。</p>
<p>来源字段：{e(json.dumps(AMOUNT_FIELDS, ensure_ascii=False))}</p><p>数据指纹：{e(history['fingerprint'])}</p></html>'''
