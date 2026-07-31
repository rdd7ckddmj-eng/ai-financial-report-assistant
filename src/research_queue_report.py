"""Build a portable, source-linked watchlist research task brief."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from html import escape

from src.china_stock import is_allowed_disclosure_url
from src.market_radar import ResearchQueueRow


def _text(value: object) -> str:
    """Escape public-source and user-facing text before HTML insertion."""
    return escape(str(value), quote=True)


def _format_percent(value: float | None) -> str:
    return "数据不足" if value is None else f"{value:.1%}"


def _format_multiple(value: float | None) -> str:
    return "数据不足" if value is None else f"{value:.2f} 倍"


def _priority_class(priority: str) -> str:
    if priority.startswith("P1"):
        return "p1"
    if priority.startswith("P2"):
        return "p2"
    return "p3"


def _disclosure_html(row: ResearchQueueRow) -> str:
    disclosure = row["latest_disclosure"]
    if disclosure is None:
        return (
            '<div class="empty">官方公告：'
            f"{_text(row['disclosure_status'])}。"
            "本简报未使用新闻摘要或 AI 猜测填补。</div>"
        )

    source_url = str(disclosure["source_url"]).strip()
    source_link = (
        f'<a href="{_text(source_url)}" target="_blank" '
        'rel="noopener noreferrer">查看官方原文 ↗</a>'
        if is_allowed_disclosure_url(source_url)
        else '<span class="muted">原文链接未通过官方域名校验</span>'
    )
    return """
    <div class="disclosure">
      <div>
        <strong>{title}</strong>
        <p>{published_date}｜{category}｜关注程度：{attention}｜
        距扫描日 {days_old} 天</p>
      </div>
      {source_link}
    </div>
    """.format(
        title=_text(disclosure["title"]),
        published_date=_text(disclosure["published_date"]),
        category=_text(disclosure["category"]),
        attention=_text(disclosure["attention"]),
        days_old=disclosure["days_old"],
        source_link=source_link,
    )


def _task_html(rank: int, row: ResearchQueueRow) -> str:
    company = row["company"]
    signals = (
        "、".join(row["triggered_signals"])
        if row["triggered_signals"]
        else "未触发三项门槛"
    )
    reasons = "".join(
        f"<li>{_text(reason)}</li>" for reason in row["research_reasons"]
    )
    priority = row["research_priority"]
    return """
    <article class="task {priority_class}">
      <div class="task-heading">
        <div>
          <span class="rank">{rank}</span>
          <h2>{company_name}｜{canonical_code}</h2>
          <p>{exchange_name}｜行情日期 {latest_date}</p>
        </div>
        <span class="priority">{priority}</span>
      </div>
      <section class="metrics">
        <div><span>最新日涨跌幅</span><strong>{daily_return}</strong></div>
        <div><span>成交量 / 前20日</span><strong>{volume_ratio}</strong></div>
        <div><span>普通换手率</span><strong>{turnover}</strong></div>
        <div><span>换手率历史分位</span><strong>{turnover_percentile}</strong></div>
      </section>
      <div class="evidence">
        <strong>行情状态：{radar_status}</strong>
        <p>触发证据：{signals}｜可用证据
        {available_count}/3 项。</p>
        <ul>{reasons}</ul>
      </div>
      <h3>最近官方公告</h3>
      {disclosure}
      <div class="sources">
        <p><strong>行情来源：</strong>{market_source}</p>
        <p><strong>换手率来源：</strong>{turnover_source}</p>
      </div>
    </article>
    """.format(
        priority_class=_priority_class(priority),
        rank=rank,
        company_name=_text(company["name"]),
        canonical_code=_text(company["canonical_code"]),
        exchange_name=_text(company["exchange_name"]),
        latest_date=_text(row["latest_date"]),
        priority=_text(priority),
        daily_return=_format_percent(row["daily_return"]),
        volume_ratio=_format_multiple(row["volume_ratio_20d"]),
        turnover=_format_percent(row["turnover"]),
        turnover_percentile=_format_percent(
            row["turnover_percentile_250d"]
        ),
        radar_status=_text(row["radar_status"]),
        signals=_text(signals),
        available_count=row["available_signal_count"],
        reasons=reasons,
        disclosure=_disclosure_html(row),
        market_source=_text(row["market_source"]),
        turnover_source=_text(row["turnover_source"]),
    )


def build_research_queue_report_html(
    rows: Sequence[ResearchQueueRow],
    *,
    scan_date: date,
    failures: Sequence[str] = (),
) -> str:
    """Return an offline HTML brief using only already-verified queue data."""
    p1_count = sum(
        row["research_priority"].startswith("P1") for row in rows
    )
    p2_count = sum(
        row["research_priority"].startswith("P2") for row in rows
    )
    p3_count = len(rows) - p1_count - p2_count
    task_items = "".join(
        _task_html(rank, row) for rank, row in enumerate(rows, start=1)
    )
    failure_items = "".join(
        f"<li>{_text(failure)}</li>" for failure in failures
    )
    failure_section = (
        "<h2>未完成扫描</h2>"
        '<div class="empty"><ul>'
        f"{failure_items}</ul>"
        "失败记录没有用旧样例或 AI 猜测替代。</div>"
        if failures
        else ""
    )

    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WFZ 自选股研究任务简报 {scan_date}</title>
  <style>
    :root {{
      --navy: #0b1f3a; --teal: #0f9b8e; --ink: #14233a;
      --muted: #617187; --line: #dce5ec; --soft: #f3f7f9;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; background: #edf2f5; color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "PingFang SC",
        "Microsoft YaHei", Arial, sans-serif; line-height: 1.6;
    }}
    .report {{
      width: min(1040px, calc(100% - 32px)); margin: 32px auto;
      background: white; border-radius: 22px; overflow: hidden;
      box-shadow: 0 18px 60px rgba(11, 31, 58, 0.12);
    }}
    header {{
      padding: 40px 46px 34px; color: white;
      background: linear-gradient(120deg, var(--navy), #123f63 58%, var(--teal));
    }}
    .eyebrow {{ font-size: 12px; font-weight: 800; letter-spacing: .16em; opacity: .82; }}
    h1 {{ margin: 6px 0; font-size: 30px; }}
    header p {{ margin: 7px 0 0; opacity: .88; }}
    main {{ padding: 34px 46px 42px; }}
    .summary {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }}
    .summary div, .metrics div {{
      padding: 15px; border: 1px solid var(--line); border-radius: 13px;
      background: white;
    }}
    .summary span, .metrics span {{ display: block; color: var(--muted); font-size: 13px; }}
    .summary strong, .metrics strong {{ display: block; margin-top: 4px; font-size: 20px; }}
    .rule {{ margin: 24px 0; padding: 17px 19px; border-left: 4px solid var(--teal); background: var(--soft); }}
    .task {{
      margin: 22px 0; padding: 22px; border: 1px solid var(--line);
      border-top: 5px solid #7d8a99; border-radius: 16px; break-inside: avoid;
    }}
    .task.p1 {{ border-top-color: #c24a3b; }}
    .task.p2 {{ border-top-color: #d4902f; }}
    .task.p3 {{ border-top-color: var(--teal); }}
    .task-heading, .disclosure {{ display: flex; justify-content: space-between; gap: 18px; align-items: flex-start; }}
    .task-heading h2 {{ display: inline; margin: 0 0 0 9px; font-size: 21px; }}
    .task-heading p, .disclosure p, .sources p {{ margin: 5px 0; color: var(--muted); font-size: 14px; }}
    .rank {{ display: inline-grid; place-items: center; width: 28px; height: 28px; border-radius: 50%; background: var(--navy); color: white; font-weight: 800; }}
    .priority {{ padding: 6px 10px; border-radius: 999px; background: #e8f3f2; font-weight: 800; white-space: nowrap; }}
    .metrics {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 18px 0; }}
    .evidence, .sources, .empty {{ padding: 15px 17px; border-radius: 12px; background: var(--soft); }}
    .evidence p, .evidence ul {{ margin: 6px 0; }}
    h3 {{ margin: 20px 0 8px; font-size: 16px; }}
    .disclosure {{ padding: 14px 0; border-bottom: 1px solid var(--line); }}
    .disclosure a {{ color: #087f75; font-weight: 800; text-decoration: none; white-space: nowrap; }}
    .sources {{ margin-top: 14px; }}
    .muted {{ color: var(--muted); font-size: 13px; }}
    .boundary {{ margin-top: 28px; padding: 18px; border: 1px solid #efd39c; border-radius: 13px; background: #fff9ed; }}
    footer {{ padding: 20px 46px; border-top: 1px solid var(--line); color: var(--muted); font-size: 13px; }}
    @media (max-width: 760px) {{
      header, main, footer {{ padding-left: 22px; padding-right: 22px; }}
      .summary, .metrics {{ grid-template-columns: 1fr 1fr; }}
      .task-heading, .disclosure {{ flex-direction: column; }}
    }}
    @media print {{
      @page {{ size: A4; margin: 12mm; }}
      body {{ background: white; }}
      .report {{ width: 100%; margin: 0; box-shadow: none; border-radius: 0; }}
    }}
  </style>
</head>
<body>
  <div class="report">
    <header>
      <div class="eyebrow">WFZ · AGENT RESEARCH DELIVERY</div>
      <h1>自选股研究任务简报</h1>
      <p>扫描日期：{scan_date}｜王方正 · Durham University · Fangzheng AI</p>
    </header>
    <main>
      <section class="summary">
        <div><span>成功扫描</span><strong>{row_count} 家</strong></div>
        <div><span>P1 立即核查</span><strong>{p1_count} 家</strong></div>
        <div><span>P2 优先复盘</span><strong>{p2_count} 家</strong></div>
        <div><span>P3 常规跟踪</span><strong>{p3_count} 家</strong></div>
      </section>
      <div class="rule">
        <strong>任务规则</strong><br>
        P1：复合行情异动或两天内高关注官方公告；
        P2：单项行情异动或七天内高/中关注官方公告；
        其他为 P3。优先级只安排研究顺序。
      </div>
      {task_items}
      {failure_section}
      <section class="boundary">
        <strong>研究边界</strong>
        <p>本简报只使用扫描时已经取得的公开行情和官方公告。
        公告关注程度是标题主题分类，不表示利好或利空；
        公告与行情时间接近不证明因果关系。普通换手率不等于有效换手率。
        P1/P2/P3不是投资评分，本简报不预测价格，也不构成买入、卖出或持有建议。</p>
      </section>
    </main>
    <footer>
      由 Fangzheng AI Financial Research Assistant 根据页面已核验结果生成。
      文件可离线打开，也可通过浏览器“打印”另存为 PDF。
    </footer>
  </div>
</body>
</html>
""".format(
        scan_date=_text(scan_date.isoformat()),
        row_count=len(rows),
        p1_count=p1_count,
        p2_count=p2_count,
        p3_count=p3_count,
        task_items=task_items,
        failure_section=failure_section,
    )
