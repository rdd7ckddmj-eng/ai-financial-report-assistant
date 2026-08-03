"""Portable, source-linked report for a financial anomaly explanation."""

from __future__ import annotations

import json
from hashlib import sha256
from html import escape
from urllib.parse import urlparse

from src.financial_anomaly_explanation import FinancialAnomalyReview
from src.financial_history import ALLOWED_REPORT_HOSTS


def _text(value: object) -> str:
    return escape(str(value), quote=True)


def _safe_source_url(value: object) -> str | None:
    url = str(value or "").strip()
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_REPORT_HOSTS:
        return None
    return url


def _percent(value: object) -> str:
    return f"{float(value):.1%}"


def _amount(value: object) -> str:
    return f"{float(value) / 100_000_000:,.2f} 亿元"


def build_financial_anomaly_audit_payload(
    review: FinancialAnomalyReview,
) -> dict[str, object]:
    """Create a stable JSON-safe evidence package with a content fingerprint."""
    payload_core: dict[str, object] = {
        "company": {
            "code": str(review["company_code"]),
            "name": str(review["company_name"]),
            "canonical_code": str(review["canonical_code"]),
        },
        "case": {
            "period_year": int(review["period_year"]),
            "comparison_year": int(review["comparison_year"]),
            "signal_detected": bool(review["signal_detected"]),
            "signal_label": str(review["signal_label"]),
        },
        "trend_signal": {
            "revenue_growth": float(review["revenue_growth"]),
            "attributable_net_profit_growth": float(
                review["attributable_net_profit_growth"]
            ),
            "operating_cash_flow_growth": float(
                review["operating_cash_flow_growth"]
            ),
        },
        "cash_flow_bridge": {
            "operating_cash_flow_current": float(
                review["operating_cash_flow_current"]
            ),
            "operating_cash_flow_comparison": float(
                review["operating_cash_flow_comparison"]
            ),
            "operating_cash_flow_change": float(
                review["operating_cash_flow_change"]
            ),
            "bridge_current_total": float(review["bridge_current_total"]),
            "bridge_comparison_total": float(
                review["bridge_comparison_total"]
            ),
            "bridge_change_total": float(review["bridge_change_total"]),
            "reconciliation_passed": bool(
                review["reconciliation_passed"]
            ),
            "drivers": [dict(driver) for driver in review["drivers"]],
        },
        "confirmed_findings": list(review["confirmed_findings"]),
        "unresolved_questions": list(review["unresolved_questions"]),
        "evidence": {
            "grade": str(review["evidence_grade"]),
            "verification_status": str(review["verification_status"]),
            "report_title": str(review["report_title"]),
            "source_url": _safe_source_url(review["source_url"]),
            "source_page": int(review["source_page"]),
        },
        "limitation": str(review["limitation"]),
        "audit_boundary": [
            "已证实项只来自确定性计算和已核验年报。",
            "待核查问题不是已证实原因。",
            "证据指纹用于识别本次数据包，不是数字签名。",
            "本报告不构成买入、卖出或持有建议。",
        ],
    }
    canonical = json.dumps(
        payload_core,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return {
        "schema_version": "1.0",
        "report_type": "wfz_financial_anomaly_explanation",
        "evidence_fingerprint": {
            "algorithm": "SHA-256",
            "value": sha256(canonical).hexdigest(),
            "scope": "除本指纹字段外的结构化证据包",
        },
        **payload_core,
    }


def build_financial_anomaly_report_html(
    review: FinancialAnomalyReview,
) -> str:
    """Render one offline Chinese report from already-verified evidence."""
    payload = build_financial_anomaly_audit_payload(review)
    fingerprint = payload["evidence_fingerprint"]["value"]
    finding_items = "".join(
        f"<li>{_text(item)}</li>" for item in review["confirmed_findings"]
    )
    question_items = "".join(
        f"<li>{_text(item)}</li>" for item in review["unresolved_questions"]
    )
    driver_rows = "".join(
        "<tr>"
        f"<td>{driver['rank']}</td>"
        f"<td>{_text(driver['component_label'])}</td>"
        f"<td>{_text(driver['direction'])}</td>"
        f"<td>{_text(_amount(driver['comparison_value']))}</td>"
        f"<td>{_text(_amount(driver['current_value']))}</td>"
        f"<td>{_text(_amount(driver['change_contribution']))}</td>"
        "</tr>"
        for driver in review["drivers"]
    )
    safe_url = _safe_source_url(review["source_url"])
    source_link = (
        f'<a href="{_text(safe_url)}" target="_blank" '
        'rel="noopener noreferrer">查看官方年报 ↗</a>'
        if safe_url
        else '<span class="muted">官方链接未通过域名校验</span>'
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_text(review['company_name'])}财务异常解释报告</title>
  <style>
    :root {{ --navy:#0b1f3a; --teal:#0f9b8e; --ink:#14233a;
      --muted:#64748b; --line:#dce5ec; --soft:#f3f7f9; --amber:#a96809; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:#edf2f5; color:var(--ink);
      font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",
      "Microsoft YaHei",Arial,sans-serif; line-height:1.65; }}
    .report {{ width:min(1040px,calc(100% - 32px)); margin:32px auto;
      background:white; border-radius:22px; overflow:hidden;
      box-shadow:0 18px 60px rgba(11,31,58,.12); }}
    header {{ padding:40px 46px 34px; color:white;
      background:linear-gradient(120deg,var(--navy),#123f63 58%,var(--teal)); }}
    .eyebrow {{ font-size:12px; font-weight:800; letter-spacing:.16em;
      opacity:.82; }}
    h1 {{ margin:7px 0; font-size:30px; }}
    header p {{ margin:5px 0; opacity:.9; }}
    main {{ padding:34px 46px 42px; }}
    .metrics {{ display:grid; grid-template-columns:repeat(3,1fr);
      gap:12px; margin-bottom:20px; }}
    .metrics div {{ border:1px solid var(--line); border-radius:14px;
      padding:16px; }}
    .metrics span {{ color:var(--muted); display:block; font-size:13px; }}
    .metrics strong {{ display:block; margin-top:4px; font-size:22px; }}
    .signal {{ padding:18px 20px; border-left:5px solid var(--amber);
      background:#fff8e8; border-radius:10px; }}
    h2 {{ margin-top:30px; font-size:21px; }}
    table {{ width:100%; border-collapse:collapse; font-size:14px; }}
    th,td {{ padding:10px 8px; border-bottom:1px solid var(--line);
      text-align:right; }}
    th:nth-child(2),td:nth-child(2) {{ text-align:left; }}
    .verified,.questions,.source {{ padding:18px 20px; border-radius:13px;
      margin-top:14px; }}
    .verified {{ background:#edf8f5; }}
    .questions {{ background:#fff8e8; }}
    .source {{ background:var(--soft); }}
    a {{ color:#087f75; font-weight:800; text-decoration:none; }}
    .muted {{ color:var(--muted); }}
    footer {{ padding:20px 46px; border-top:1px solid var(--line);
      color:var(--muted); font-size:13px; overflow-wrap:anywhere; }}
    @media(max-width:760px) {{ header,main,footer {{ padding-left:22px;
      padding-right:22px; }} .metrics {{ grid-template-columns:1fr; }}
      table {{ font-size:12px; }} }}
    @media print {{ @page {{ size:A4; margin:12mm; }} body {{ background:white; }}
      .report {{ width:100%; margin:0; box-shadow:none; border-radius:0; }} }}
  </style>
</head>
<body><div class="report">
  <header>
    <div class="eyebrow">FANGZHENG AI · FINANCIAL EXPLANATION AGENT</div>
    <h1>{_text(review['company_name'])}｜财务异常解释</h1>
    <p>{_text(review['canonical_code'])}｜
      {review['comparison_year']}—{review['period_year']}</p>
    <p>王方正 · Durham University · Fangzheng AI</p>
  </header>
  <main>
    <section class="metrics">
      <div><span>营业收入同比</span>
        <strong>{_percent(review['revenue_growth'])}</strong></div>
      <div><span>归母净利润同比</span>
        <strong>{_percent(review['attributable_net_profit_growth'])}</strong></div>
      <div><span>经营现金流同比</span>
        <strong>{_percent(review['operating_cash_flow_growth'])}</strong></div>
    </section>
    <div class="signal"><strong>规则识别：</strong>{_text(review['signal_label'])}</div>
    <h2>已证实的算术桥接</h2>
    <div class="verified"><ul>{finding_items}</ul></div>
    <h2>现金流变化贡献排名</h2>
    <table><thead><tr><th>#</th><th>调节项</th><th>方向</th>
      <th>{review['comparison_year']}</th><th>{review['period_year']}</th><th>同比贡献</th>
    </tr></thead><tbody>{driver_rows}</tbody></table>
    <h2>待进一步核查</h2>
    <div class="questions"><ul>{question_items}</ul></div>
    <h2>证据来源</h2>
    <div class="source"><strong>{_text(review['report_title'])}</strong><br>
      第 {review['source_page']} 页｜证据等级 {_text(review['evidence_grade'])}｜
      {_text(review['verification_status'])}<br>{source_link}</div>
    <h2>研究边界</h2><p>{_text(review['limitation'])}</p>
  </main>
  <footer>证据指纹（SHA-256）：{_text(fingerprint)}</footer>
</div></body></html>"""
