"""Build a self-contained, auditable market-anomaly research report card."""

from __future__ import annotations

import re
from datetime import date
from html import escape
from urllib.parse import (
    parse_qsl,
    urlencode,
    urlparse,
    urlsplit,
    urlunsplit,
)

from src.anomaly_analogs import AnomalyAnalog
from src.china_stock import CompanyIdentity, MarketActivityEvent
from src.historical_lens import EventEvidenceChain


def _text(value: object) -> str:
    """Escape external text before placing it in the downloadable HTML."""
    return escape(str(value), quote=True)


def _safe_http_url(value: object) -> str | None:
    """Return only explicit HTTP(S) links for downloadable reports."""
    candidate = str(value).strip()
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return escape(candidate, quote=True)


def _historical_lens_link(
    base_url: object,
    company_code: object,
    event_date: object,
) -> str | None:
    """Build one safe replay link without trusting report data as URL text."""
    candidate_url = str(base_url).strip()
    code = str(company_code).strip()
    event_date_text = str(event_date).strip()
    parsed = urlsplit(candidate_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if re.fullmatch(r"\d{6}", code) is None:
        return None
    try:
        date.fromisoformat(event_date_text)
    except ValueError:
        return None

    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key not in {"code", "date", "source"}
    ]
    query_items.extend(
        [
            ("code", code),
            ("date", event_date_text),
            ("source", "anomaly-report"),
        ]
    )
    linked_url = urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(query_items),
            parsed.fragment,
        )
    )
    return escape(linked_url, quote=True)


def _format_percent(value: float | None) -> str:
    return "数据不足" if value is None else f"{value:.1%}"


def _format_multiple(value: float | None) -> str:
    return "数据不足" if value is None else f"{value:.2f} 倍"


def _evidence_html(chain: EventEvidenceChain | None) -> str:
    if chain is None:
        return """
        <div class="empty">
          官方公告源暂时不可访问。本报告没有使用新闻、搜索摘要或
          AI 推测替代官方公告。
        </div>
        """

    if not chain["matches"]:
        return (
            '<div class="empty">'
            f"{_text(chain['conclusion'])}"
            "</div>"
        )

    items: list[str] = []
    for item in chain["matches"]:
        source_url = _safe_http_url(item["source_url"])
        link = (
            f'<a href="{source_url}" target="_blank" '
            'rel="noopener noreferrer">查看官方原文 ↗</a>'
            if source_url
            else '<span class="muted">原文链接未通过安全校验</span>'
        )
        items.append(
            """
            <article class="evidence-item">
              <div>
                <strong>{title}</strong>
                <p>{relation} · {date} · {source_type} · 证据等级 {grade}</p>
              </div>
              {link}
            </article>
            """.format(
                title=_text(item["title"]),
                relation=_text(item["relation"]),
                date=_text(item["published_date"]),
                source_type=_text(item["source_type"]),
                grade=_text(item["evidence_grade"]),
                link=link,
            )
        )
    return "".join(items)


def _analogs_html(
    analogs: list[AnomalyAnalog],
    historical_lens_url: str | None,
    company_code: str,
) -> str:
    """Format already-computed analogs without fetching later outcomes."""
    if not analogs:
        return """
        <div class="empty">
          当前扫描范围内没有达到最低门槛的更早相似异动。
        </div>
        """

    items: list[str] = []
    for rank, analog in enumerate(analogs, start=1):
        comparison_note = (
            f"共同信号：{'、'.join(analog['shared_signals'])}。"
            if analog["shared_signals"]
            else analog["comparison_summary"]
        )
        replay_url = (
            _historical_lens_link(
                historical_lens_url,
                company_code,
                analog["date"],
            )
            if historical_lens_url is not None
            else None
        )
        replay_link = (
            f'<a class="replay-link" href="{replay_url}" '
            'target="_blank" rel="noopener noreferrer">'
            f"直接复盘 {_text(analog['date'])} ↗</a>"
            if replay_url
            else '<span class="muted">Historical Lens 链接暂未配置</span>'
        )
        items.append(
            """
            <article class="analog-item">
              <div class="analog-heading">
                <strong>{rank}. {date}｜{event_type}</strong>
                <span class="score">规则相似度 {similarity}</span>
              </div>
              <p>{comparison_note}</p>
              <p>日涨跌幅 {daily_return}｜成交量 / 前20日中位数
              {volume_ratio}｜普通换手率历史分位
              {turnover_percentile}｜可比维度 {dimension_count} 项。</p>
              {replay_link}
            </article>
            """.format(
                rank=rank,
                date=_text(analog["date"]),
                event_type=_text(analog["event_type"]),
                similarity=_format_percent(analog["similarity_score"]),
                comparison_note=_text(comparison_note),
                daily_return=_format_percent(analog["daily_return"]),
                volume_ratio=_format_multiple(analog["volume_ratio_20d"]),
                turnover_percentile=_format_percent(
                    analog["turnover_percentile_250d"]
                ),
                dimension_count=analog["comparable_dimension_count"],
                replay_link=replay_link,
            )
        )
    return "".join(items)


def build_anomaly_report_card_html(
    company: CompanyIdentity,
    event: MarketActivityEvent,
    evidence_chain: EventEvidenceChain | None,
    *,
    market_source: str,
    turnover_source: str,
    analogs: list[AnomalyAnalog] | None = None,
    historical_lens_url: str | None = None,
) -> str:
    """Return a portable HTML report using only already-verified page data."""
    evidence_status = (
        "官方公告源暂时不可访问"
        if evidence_chain is None
        else evidence_chain["conclusion"]
    )
    future_excluded = (
        "公告源不可用，无法执行公告时间隔离审计"
        if evidence_chain is None
        else (
            f"另有 {evidence_chain['future_excluded_count']} 条研究日之后"
            "公开的公告被排除"
        )
    )
    evidence_limitation = (
        "本次未取得官方公告，因此不对异常原因作任何解释。"
        if evidence_chain is None
        else evidence_chain["limitation"]
    )
    limit_status = (
        "达到板块参考阈值"
        if event["limit_up_candidate"]
        else "未达到板块参考阈值"
    )
    turnover_status = (
        "达到历史高位候选门槛"
        if event["turnover_high_candidate"]
        else "未达到历史高位候选门槛"
    )
    analog_items = _analogs_html(
        analogs or [],
        historical_lens_url,
        company["code"],
    )

    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{company_name} {event_date} 异动研究报告</title>
  <style>
    :root {{
      --navy: #0b1f3a;
      --teal: #0f9b8e;
      --ink: #14233a;
      --muted: #5f6f82;
      --line: #dce5ec;
      --soft: #eef5f7;
      --paper: #ffffff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: #edf2f5;
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "PingFang SC",
        "Microsoft YaHei", Arial, sans-serif;
      line-height: 1.6;
    }}
    .report {{
      width: min(960px, calc(100% - 32px));
      margin: 32px auto;
      background: var(--paper);
      border-radius: 22px;
      box-shadow: 0 18px 60px rgba(11, 31, 58, 0.12);
      overflow: hidden;
    }}
    header {{
      padding: 40px 46px 34px;
      color: white;
      background: linear-gradient(120deg, var(--navy), #123f63 58%, var(--teal));
    }}
    .eyebrow {{
      margin: 0 0 8px;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.18em;
      opacity: 0.82;
    }}
    h1 {{ margin: 0; font-size: 30px; line-height: 1.25; }}
    header .meta {{ margin: 14px 0 0; opacity: 0.86; }}
    main {{ padding: 34px 46px 42px; }}
    h2 {{ margin: 34px 0 14px; font-size: 20px; color: var(--navy); }}
    h2:first-child {{ margin-top: 0; }}
    .summary {{
      padding: 18px 20px;
      border-left: 4px solid var(--teal);
      border-radius: 0 12px 12px 0;
      background: var(--soft);
      font-weight: 600;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
    }}
    .metric {{
      padding: 16px;
      border: 1px solid var(--line);
      border-radius: 14px;
    }}
    .metric span {{ display: block; color: var(--muted); font-size: 13px; }}
    .metric strong {{ display: block; margin-top: 5px; font-size: 21px; }}
    .audit {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }}
    .audit div, .source, .risk {{
      padding: 15px 17px;
      border: 1px solid var(--line);
      border-radius: 12px;
    }}
    .audit p, .source p, .risk p, .evidence-item p {{
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 14px;
    }}
    .evidence-item {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 20px;
      padding: 16px 0;
      border-bottom: 1px solid var(--line);
    }}
    .evidence-item a {{
      flex: 0 0 auto;
      color: #087f75;
      font-weight: 700;
      text-decoration: none;
    }}
    .analog-item {{
      margin-bottom: 12px;
      padding: 16px 18px;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: #fbfdfe;
    }}
    .analog-heading {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
    }}
    .analog-item p {{
      margin: 6px 0;
      color: var(--muted);
      font-size: 14px;
    }}
    .score {{
      flex: 0 0 auto;
      padding: 4px 9px;
      border-radius: 999px;
      background: #dff3ef;
      color: #087f75;
      font-size: 12px;
      font-weight: 800;
    }}
    .replay-link {{
      display: inline-block;
      margin-top: 7px;
      color: #087f75;
      font-weight: 700;
      text-decoration: none;
    }}
    .empty {{
      padding: 17px;
      border: 1px dashed #9fb0be;
      border-radius: 12px;
      color: var(--muted);
    }}
    .muted {{ color: var(--muted); font-size: 13px; }}
    .risk {{ border-color: #f0d39b; background: #fff9ed; }}
    footer {{
      padding: 20px 46px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 13px;
    }}
    @media (max-width: 700px) {{
      header, main, footer {{ padding-left: 24px; padding-right: 24px; }}
      .grid, .audit {{ grid-template-columns: 1fr; }}
      .evidence-item {{ align-items: flex-start; flex-direction: column; gap: 8px; }}
      .analog-heading {{
        align-items: flex-start;
        flex-direction: column;
        gap: 6px;
      }}
    }}
    @media print {{
      @page {{ size: A4; margin: 12mm; }}
      body {{ background: white; }}
      .report {{
        width: 100%;
        margin: 0;
        border-radius: 0;
        box-shadow: none;
      }}
      .evidence-item {{ break-inside: avoid; }}
    }}
  </style>
</head>
<body>
  <div class="report">
    <header>
      <p class="eyebrow">WFZ · MARKET ANOMALY RESEARCH</p>
      <h1>中国上市公司异动研究报告</h1>
      <p class="meta">王方正 · Durham University · Fangzheng AI</p>
    </header>
    <main>
      <h2>研究对象</h2>
      <div class="summary">
        {company_name} · {canonical_code} · {exchange_name}<br>
        研究日期：{event_date} · 系统分型：{event_type}
      </div>

      <h2>当日市场证据</h2>
      <section class="grid">
        <div class="metric"><span>收盘价</span><strong>¥{close}</strong></div>
        <div class="metric"><span>日涨跌幅</span><strong>{daily_return}</strong></div>
        <div class="metric"><span>成交量 / 前20日中位数</span><strong>{volume_ratio}</strong></div>
        <div class="metric"><span>成交量历史分位</span><strong>{volume_percentile}</strong></div>
        <div class="metric"><span>普通换手率</span><strong>{turnover}</strong></div>
        <div class="metric"><span>换手率历史分位</span><strong>{turnover_percentile}</strong></div>
      </section>

      <h2>规则审计</h2>
      <section class="audit">
        <div>
          <strong>涨跌幅规则</strong>
          <p>{limit_status}；参考阈值 {limit_reference}。<br>
          涨跌幅口径：{return_basis}。</p>
        </div>
        <div>
          <strong>换手率规则</strong>
          <p>{turnover_status}。普通换手率不等同于有效换手率。</p>
        </div>
      </section>

      <h2>官方公告证据链</h2>
      <p>{evidence_status}</p>
      {evidence_items}
      <p class="muted">时间隔离审计：{future_excluded}。</p>

      <h2>历史相似异动</h2>
      <p>以下案例只来自研究日期以前，并按确定性规则比较信号组合、
      日涨跌幅、成交量倍数和普通换手率历史分位。缺失维度已退出计算，
      后来收益没有进入本报告。</p>
      {analog_items}
      <p class="muted">相似度只描述历史形态接近程度，不是股价预测，
      也不构成投资建议。</p>

      <h2>数据来源</h2>
      <section class="source">
        <strong>行情</strong>
        <p>{market_source}</p>
        <strong>普通换手率</strong>
        <p>{turnover_source}</p>
      </section>

      <h2>研究边界</h2>
      <section class="risk">
        <strong>请按证据阅读，不按结论交易</strong>
        <p>{evidence_limitation}</p>
        <p>前复权日线仅用于连续趋势和异动筛选；历史分位只使用目标日之前
        的数据，不包含目标日自身和未来交易日。本文档不预测股价，不认定
        公告与行情存在因果关系，也不构成买入、卖出或持有建议。</p>
      </section>
    </main>
    <footer>
      由 Fangzheng AI Financial Research Assistant 根据页面中已经核验的
      确定性计算结果生成。可使用浏览器的“打印”功能另存为 PDF。
    </footer>
  </div>
</body>
</html>
""".format(
        company_name=_text(company["name"]),
        canonical_code=_text(company["canonical_code"]),
        exchange_name=_text(company["exchange_name"]),
        event_date=_text(event["date"]),
        event_type=_text(event["event_type"]),
        close=f"{event['close']:,.2f}",
        daily_return=_format_percent(event["daily_return"]),
        volume_ratio=_format_multiple(event["volume_ratio_20d"]),
        volume_percentile=_format_percent(
            event["volume_percentile_250d"]
        ),
        turnover=_format_percent(event["turnover"]),
        turnover_percentile=_format_percent(
            event["turnover_percentile_250d"]
        ),
        limit_status=limit_status,
        limit_reference=_format_percent(event["limit_up_reference"]),
        return_basis=_text(event["daily_return_basis"]),
        turnover_status=turnover_status,
        evidence_status=_text(evidence_status),
        evidence_items=_evidence_html(evidence_chain),
        future_excluded=_text(future_excluded),
        analog_items=analog_items,
        market_source=_text(market_source),
        turnover_source=_text(turnover_source),
        evidence_limitation=_text(evidence_limitation),
    )
