"""Render a self-contained HTML export for one comprehensive research run."""

from __future__ import annotations

from collections.abc import Mapping
from html import escape

from src.china_stock import is_allowed_disclosure_url
from src.comprehensive_research import ComprehensiveResearchBrief


STATUS_LABELS = {
    "verified": "已核验",
    "partial": "部分证据",
    "unavailable": "暂不可用",
}


def _text(value: object) -> str:
    return escape(str(value), quote=True)


def _source_link(url: str | None) -> str:
    if not url:
        return '<span class="muted">本项没有可展示的官方链接</span>'
    return (
        f'<a href="{_text(url)}" target="_blank" '
        'rel="noopener noreferrer">查看官方证据 ↗</a>'
    )


def _lane_html(lane: dict[str, object]) -> str:
    status = str(lane["status"])
    return """
    <article class="lane {status}">
      <div class="lane-head">
        <h3>{label}</h3>
        <span>{status_label}</span>
      </div>
      <p>{summary}</p>
      <div class="meta">来源：{source}</div>
      <div class="meta">截止：{as_of_date}</div>
      <div class="limit">{limitation}</div>
      {source_link}
    </article>
    """.format(
        status=_text(status),
        label=_text(lane["label"]),
        status_label=_text(STATUS_LABELS.get(status, "待核验")),
        summary=_text(lane["summary"]),
        source=_text(lane["source"]),
        as_of_date=_text(lane.get("as_of_date") or "不适用"),
        limitation=_text(lane["limitation"]),
        source_link=_source_link(
            str(lane["source_url"]) if lane.get("source_url") else None
        ),
    )


def _finding_html(finding: dict[str, object]) -> str:
    status = str(finding["status"])
    return """
    <article class="finding">
      <div class="finding-head">
        <span class="category">{category}</span>
        <span class="status {status}">{status_label}</span>
      </div>
      <h3>{headline}</h3>
      <p>{statement}</p>
      <div class="basis"><strong>依据：</strong>{basis}</div>
      {source_link}
    </article>
    """.format(
        category=_text(finding["category"]),
        status=_text(status),
        status_label=_text(STATUS_LABELS.get(status, "待核验")),
        headline=_text(finding["headline"]),
        statement=_text(finding["statement"]),
        basis=_text(finding["basis"]),
        source_link=_source_link(
            str(finding["source_url"])
            if finding.get("source_url")
            else None
        ),
    )


def _action_html(action: dict[str, object]) -> str:
    return """
    <li>
      <span class="priority">P{priority}</span>
      <div><strong>{label}</strong><p>{reason}</p></div>
    </li>
    """.format(
        priority=_text(action["priority"]),
        label=_text(action["label"]),
        reason=_text(action["reason"]),
    )


def _trace_html(step: dict[str, object]) -> str:
    status = str(step["status"])
    return """
    <tr>
      <td>{sequence:02d}</td>
      <td><strong>{agent}</strong><br><span>{task}</span></td>
      <td><span class="status {status}">{status_label}</span></td>
      <td>{output}</td>
    </tr>
    """.format(
        sequence=int(step["sequence"]),
        agent=_text(step["agent"]),
        task=_text(step["task"]),
        status=_text(status),
        status_label=_text(STATUS_LABELS.get(status, "待核验")),
        output=_text(step["output"]),
    )


def _radar_context_html(
    context: Mapping[str, object] | None,
    *,
    canonical_code: str,
) -> str:
    """Render the research trigger only for the report's selected company."""
    if context is None or context.get("canonical_code") != canonical_code:
        return ""

    signals = context.get("triggered_signals")
    signal_text = (
        "、".join(_text(item) for item in signals)
        if isinstance(signals, list) and signals
        else "未触发三项门槛"
    )
    reasons = context.get("research_reasons")
    reason_items = (
        "".join(f"<li>{_text(item)}</li>" for item in reasons)
        if isinstance(reasons, list) and reasons
        else "<li>等待综合研究重新核验</li>"
    )

    latest_disclosure = context.get("latest_disclosure")
    if isinstance(latest_disclosure, Mapping):
        raw_url = str(latest_disclosure.get("source_url", "")).strip()
        disclosure_link = _source_link(
            raw_url if is_allowed_disclosure_url(raw_url) else None
        )
        disclosure_html = """
        <div class="trigger-disclosure">
          <strong>雷达已找到的最近官方公告</strong>
          <p>{title}</p>
          <div class="meta">
            {published_date}｜{category}｜关注程度：{attention}｜{status}
          </div>
          {source_link}
        </div>
        """.format(
            title=_text(latest_disclosure.get("title", "标题待核验")),
            published_date=_text(
                latest_disclosure.get("published_date", "日期待核验")
            ),
            category=_text(
                latest_disclosure.get("category", "类别待核验")
            ),
            attention=_text(
                latest_disclosure.get("attention", "待核验")
            ),
            status=_text(context.get("disclosure_status", "状态待核验")),
            source_link=disclosure_link,
        )
    else:
        disclosure_html = (
            '<div class="trigger-disclosure"><strong>官方公告状态</strong>'
            f'<p>{_text(context.get("disclosure_status", "待核验"))}</p>'
            "</div>"
        )

    return """
    <h2>研究触发来源</h2>
    <section class="trigger-card">
      <div class="trigger-label">WATCHLIST RADAR HANDOFF</div>
      <div class="trigger-grid">
        <div><span>研究顺序</span><strong>{priority}</strong></div>
        <div><span>雷达状态</span><strong>{radar_status}</strong></div>
        <div><span>行情日期</span><strong>{market_date}</strong></div>
        <div><span>扫描日期</span><strong>{scan_date}</strong></div>
      </div>
      <p><strong>雷达触发证据：</strong>{signal_text}</p>
      <strong>进入深度研究的原因</strong>
      <ul>{reason_items}</ul>
      {disclosure_html}
      <div class="trigger-boundary">
        本节只记录为何启动研究，不参与财务计算、证据覆盖率或投资判断；
        后续五条证据链已由综合研究 Agent 独立重新核验。
      </div>
    </section>
    """.format(
        priority=_text(context.get("research_priority", "待核验")),
        radar_status=_text(context.get("radar_status", "待核验")),
        market_date=_text(context.get("market_date", "待核验")),
        scan_date=_text(context.get("scan_date", "待核验")),
        signal_text=signal_text,
        reason_items=reason_items,
        disclosure_html=disclosure_html,
    )


def build_comprehensive_research_report_html(
    brief: ComprehensiveResearchBrief,
    *,
    radar_context: Mapping[str, object] | None = None,
) -> str:
    """Return one portable evidence-first research brief."""
    company = brief["company"]
    lane_items = "".join(_lane_html(lane) for lane in brief["evidence_lanes"])
    finding_items = "".join(
        _finding_html(finding) for finding in brief["findings"]
    ) or '<div class="empty">当前证据不足，未生成确定性观察。</div>'
    action_items = "".join(_action_html(action) for action in brief["actions"])
    trace_rows = "".join(_trace_html(step) for step in brief["trace"])
    limitations = "".join(
        f"<li>{_text(item)}</li>" for item in brief["limitations"]
    )
    coverage_percent = brief["coverage_ratio"] * 100
    radar_context_html = _radar_context_html(
        radar_context,
        canonical_code=company["canonical_code"],
    )

    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WFZ 综合研究简报｜{company_name}｜{generated_on}</title>
  <style>
    :root {{
      --navy:#081a2d; --navy2:#123753; --teal:#39c4b6;
      --ink:#17283c; --muted:#64748b; --line:#dbe5eb;
      --soft:#f2f6f8; --gold:#d6b66a; --warn:#b9742c;
    }}
    * {{ box-sizing:border-box; }}
    body {{
      margin:0; color:var(--ink); background:#eaf0f3;
      font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",
        "Microsoft YaHei",Arial,sans-serif; line-height:1.65;
    }}
    .report {{
      width:min(1120px,calc(100% - 32px)); margin:28px auto;
      background:#fff; box-shadow:0 22px 70px rgba(8,26,45,.14);
      border-radius:24px; overflow:hidden;
    }}
    header {{
      padding:42px 48px; color:#fff;
      background:linear-gradient(125deg,var(--navy),var(--navy2) 62%,#176b6d);
    }}
    .eyebrow {{ font-size:12px; letter-spacing:.18em; font-weight:800; color:#9ce0d9; }}
    h1 {{ margin:8px 0 4px; font-size:34px; }}
    header p {{ margin:5px 0; color:#d9e6ec; }}
    main {{ padding:38px 48px 48px; }}
    .summary {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:28px; }}
    .summary div {{ border:1px solid var(--line); border-radius:14px; padding:16px; background:var(--soft); }}
    .summary span {{ display:block; color:var(--muted); font-size:13px; }}
    .summary strong {{ display:block; margin-top:5px; font-size:22px; }}
    h2 {{ margin:32px 0 14px; font-size:22px; }}
    .lanes {{ display:grid; grid-template-columns:repeat(2,1fr); gap:14px; }}
    .lane,.finding {{ border:1px solid var(--line); border-radius:16px; padding:19px; break-inside:avoid; }}
    .lane-head,.finding-head {{ display:flex; justify-content:space-between; gap:12px; align-items:center; }}
    .lane h3,.finding h3 {{ margin:0; font-size:17px; }}
    .lane-head span,.status {{ padding:4px 9px; border-radius:999px; font-size:12px; font-weight:800; }}
    .verified .lane-head span,.status.verified {{ color:#087f74; background:#e3f5f2; }}
    .partial .lane-head span,.status.partial {{ color:#96601e; background:#fff1d9; }}
    .unavailable .lane-head span,.status.unavailable {{ color:#8a4650; background:#fbe8eb; }}
    .meta,.basis,.limit,.muted {{ color:var(--muted); font-size:13px; }}
    .limit {{ margin:9px 0; padding:9px 11px; border-left:3px solid var(--gold); background:#fbf8ef; }}
    a {{ color:#087f74; font-weight:800; text-decoration:none; }}
    .findings {{ display:grid; grid-template-columns:repeat(2,1fr); gap:14px; }}
    .category {{ color:#527087; font-size:12px; font-weight:800; letter-spacing:.08em; }}
    .finding h3 {{ margin:10px 0 7px; }}
    .trigger-card {{ border:1px solid #a9dcd6; border-radius:16px; padding:20px; background:#eef9f7; }}
    .trigger-label {{ color:#087f74; font-size:12px; font-weight:900; letter-spacing:.12em; }}
    .trigger-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin:14px 0; }}
    .trigger-grid div {{ padding:12px; border-radius:11px; background:#fff; border:1px solid #cce9e5; }}
    .trigger-grid span {{ display:block; color:var(--muted); font-size:12px; }}
    .trigger-grid strong {{ display:block; margin-top:4px; }}
    .trigger-disclosure {{ margin-top:14px; padding:14px; border-radius:12px; background:#fff; border:1px solid #cce9e5; }}
    .trigger-disclosure p {{ margin:5px 0; }}
    .trigger-boundary {{ margin-top:14px; padding:11px 13px; border-left:3px solid var(--teal); background:#fff; color:var(--muted); font-size:13px; }}
    .actions {{ list-style:none; margin:0; padding:0; display:grid; gap:10px; }}
    .actions li {{ display:flex; gap:14px; padding:14px; border:1px solid var(--line); border-radius:13px; }}
    .priority {{ display:grid; place-items:center; min-width:38px; height:38px; border-radius:10px; background:var(--navy); color:#fff; font-weight:900; }}
    .actions p {{ margin:3px 0 0; color:var(--muted); }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th,td {{ text-align:left; padding:12px; border-bottom:1px solid var(--line); vertical-align:top; }}
    th {{ color:var(--muted); background:var(--soft); }}
    td span {{ color:var(--muted); }}
    .boundary,.empty {{ margin-top:12px; padding:17px 19px; border-radius:14px; background:#fff8e9; border:1px solid #edd6a4; }}
    footer {{ padding:24px 48px; background:var(--navy); color:#c8d9e2; font-size:13px; }}
    @media(max-width:760px) {{
      header,main,footer {{ padding-left:24px; padding-right:24px; }}
      .summary,.lanes,.findings,.trigger-grid {{ grid-template-columns:1fr; }}
      table {{ display:block; overflow-x:auto; }}
    }}
    @media print {{ body {{ background:#fff; }} .report {{ width:100%; margin:0; box-shadow:none; }} }}
  </style>
</head>
<body>
<article class="report">
  <header>
    <div class="eyebrow">FANGZHENG AI · COMPREHENSIVE RESEARCH AGENT</div>
    <h1>{company_name}｜{canonical_code}</h1>
    <p>{exchange_name}｜研究生成日 {generated_on}</p>
    <p>确定性计算 · 官方来源 · 页码溯源 · 缺失证据显式披露</p>
  </header>
  <main>
    <section class="summary">
      <div><span>证据覆盖率</span><strong>{coverage_percent:.0f}%</strong></div>
      <div><span>覆盖状态</span><strong>{coverage_label}</strong></div>
      <div><span>已核验证据链</span><strong>{verified_count} / 5</strong></div>
      <div><span>确定性观察</span><strong>{finding_count} 项</strong></div>
    </section>

    {radar_context_html}

    <h2>证据覆盖</h2>
    <section class="lanes">{lane_items}</section>

    <h2>确定性研究观察</h2>
    <section class="findings">{finding_items}</section>

    <h2>下一步核验任务</h2>
    <ol class="actions">{action_items}</ol>

    <h2>Agent 执行轨迹</h2>
    <table>
      <thead><tr><th>步骤</th><th>角色与任务</th><th>状态</th><th>输出</th></tr></thead>
      <tbody>{trace_rows}</tbody>
    </table>

    <h2>研究边界</h2>
    <div class="boundary"><ul>{limitations}</ul></div>
  </main>
  <footer>
    WFZ 中国上市公司自主研究 Agent｜产品设计与研发：王方正 · Durham University<br>
    本简报用于教育、求职演示与研究记录，不构成投资建议。
  </footer>
</article>
</body>
</html>
""".format(
        company_name=_text(company["name"]),
        canonical_code=_text(company["canonical_code"]),
        exchange_name=_text(company["exchange_name"]),
        generated_on=_text(brief["generated_on"]),
        coverage_percent=coverage_percent,
        coverage_label=_text(brief["coverage_label"]),
        verified_count=brief["verified_lane_count"],
        finding_count=len(brief["findings"]),
        radar_context_html=radar_context_html,
        lane_items=lane_items,
        finding_items=finding_items,
        action_items=action_items,
        trace_rows=trace_rows,
        limitations=limitations,
    )
