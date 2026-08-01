"""Render a self-contained HTML export for one comprehensive research run."""

from __future__ import annotations

from html import escape

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


def build_comprehensive_research_report_html(
    brief: ComprehensiveResearchBrief,
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
      .summary,.lanes,.findings {{ grid-template-columns:1fr; }}
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
        lane_items=lane_items,
        finding_items=finding_items,
        action_items=action_items,
        trace_rows=trace_rows,
        limitations=limitations,
    )
