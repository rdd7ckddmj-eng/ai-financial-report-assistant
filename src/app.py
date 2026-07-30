import json
import sys
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()

from src.adaptive_escalation import (
    EscalationDecision,
    decide_adaptive_escalation,
)
from src.agent_coordinator import (
    AgentTraceStep,
    AgentWorkflowRun,
    build_agent_audit_record,
    run_agent_workflow,
)
from src.agent_router import RouteDecision, route_question
from src.answer_verifier import VerificationResult
from src.balance_sheet_extractor import find_balance_sheet_figures
from src.cash_flow_extractor import find_cash_flow_figures
from src.china_stock import (
    CompanyIdentity,
    DataSourceError,
    MarketActivityEvidence,
    MarketMetrics,
    add_moving_averages,
    calculate_market_activity,
    calculate_market_metrics,
    download_official_pdf,
    fetch_announcements,
    fetch_company_directory,
    fetch_market_history,
    resolve_company,
    select_latest_annual_report,
)
from src.financial_statement_extractor import find_income_statement_figures
from src.financial_ratios import (
    current_ratio,
    liabilities_to_assets_ratio,
    net_profit_margin,
    revenue_growth,
)
from src.flagship_cases import load_moutai_flagship_events
from src.historical_lens import (
    EvidenceRecord,
    calculate_historical_snapshot,
    calculate_later_outcomes,
    filter_evidence_as_of,
    slice_market_as_of,
)
from src.llm_analyst import (
    LLMAnalystRun,
    run_llm_analyst,
    serialise_llm_run,
)
from src.pdf_extractor import ExtractedPage, extract_pdf_pages
from src.qa_benchmark import (
    BenchmarkCaseResult,
    BenchmarkSummary,
    evaluate_benchmark,
    load_benchmark_cases,
    summarise_benchmark,
)
from src.report_retriever import (
    ReportChunk,
    chunk_report_pages,
)
from src.report_metric_tool import MetricToolResult


CHINESE_USER_GUIDE_PATH = (
    PROJECT_ROOT / "docs" / "中文使用说明.md"
)


def show_metric_tool_result(result: MetricToolResult) -> None:
    """Display a routed Python calculation with inputs and provenance."""
    st.markdown("#### Python 财务计算工具")
    if not result["is_available"]:
        st.warning(result["messages"][0])
        return

    st.success(f"{result['label']}: {result['display_value']}")
    st.markdown(f"**计算公式：** {result['formula']}")
    for item in result["inputs"]:
        st.markdown(f"- {item['label']}: {item['display_value']}")
    for message in result["messages"]:
        st.caption(message)
    st.caption(
        f"本结果由 Python 确定性计算。证据来源：PDF 第 "
        f"{result['source_page']} 页。"
    )


def show_route_decision(decision: RouteDecision) -> None:
    """Show which workflow the router selected and why."""
    st.markdown("#### Agent 任务路由")
    st.info(f"已选择工作流：{decision['label']}")
    st.caption(decision["reason"])
    st.markdown(" → ".join(decision["roles"]))
    trigger_text = decision["matched_trigger"] or "直接检索"
    st.caption(
        f"路由触发词：{trigger_text}。证据检索深度："
        f"{decision['top_k']} 个片段；回答证据上限："
        f"{decision['max_evidence']} 条；反方证据上限："
        f"{decision['max_challenges']} 条。"
    )


def show_escalation_decision(decision: EscalationDecision) -> None:
    """Explain whether post-retrieval signals increased analysis depth."""
    st.markdown("#### Agent 动态升级")
    if decision["escalated"]:
        st.warning(decision["summary"])
    elif decision["signals"]:
        st.warning(decision["summary"])
    else:
        st.success(decision["summary"])

    for signal in decision["signals"]:
        st.markdown(f"- {signal}")

    if decision["escalated"]:
        route = decision["route"]
        st.markdown(f"**升级后的工作流：** {route['label']}")
        st.markdown(" → ".join(route["roles"]))
        st.caption(
            f"检索范围已扩大至 {route['top_k']} 个片段；回答证据上限 "
            f"{route['max_evidence']} 条；反方证据上限 "
            f"{route['max_challenges']} 条。"
        )


def _show_trace_steps(steps: list[AgentTraceStep]) -> None:
    """Display compact role handoffs without hiding their source pages."""
    for step in steps:
        st.markdown(
            f"**{step['sequence']}. {step['role']} — "
            f"{step['status']}**"
        )
        st.caption(step["task"])
        st.write(step["output"])
        if step["source_pages"]:
            page_text = ", ".join(
                str(page) for page in step["source_pages"]
            )
            st.caption(f"PDF 证据页码：{page_text}。")


def show_agent_trace(
    initial_run: AgentWorkflowRun,
    final_run: AgentWorkflowRun,
    escalated: bool,
) -> None:
    """Show the initial and, when needed, escalated Agent handoffs."""
    st.markdown("#### 多 Agent 协调执行轨迹")
    with st.expander("初始 Agent 执行", expanded=False):
        _show_trace_steps(initial_run["trace"])

    if escalated:
        with st.expander(
            "升级后的 Agent 执行",
            expanded=False,
        ):
            _show_trace_steps(final_run["trace"])


def run_uploaded_qa_benchmark(
    pages: list[ExtractedPage],
) -> tuple[list[BenchmarkCaseResult], BenchmarkSummary]:
    """Run the human-checked Tesco Q&A cases against uploaded pages."""
    chunks = chunk_report_pages(pages)
    income_figures = find_income_statement_figures(
        (page["page_number"], page["text"]) for page in pages
    )
    balance_figures = find_balance_sheet_figures(
        (page["page_number"], page["text"]) for page in pages
    )
    results = evaluate_benchmark(
        cases=load_benchmark_cases(),
        chunks=chunks,
        income_figures=income_figures,
        balance_figures=balance_figures,
    )
    return results, summarise_benchmark(results)


def show_qa_benchmark_results(
    results: list[BenchmarkCaseResult],
    summary: BenchmarkSummary,
) -> None:
    """Show measured quality and failed cases without hiding weaknesses."""
    case_column, check_column, route_column, page_column = st.columns(4)
    case_column.metric(
        "通过案例",
        f"{summary['passed_cases']}/{summary['total_cases']}",
    )
    check_column.metric(
        "检查通过率",
        f"{summary['check_pass_rate']:.1%}",
    )
    route_column.metric(
        "路由准确率",
        f"{summary['route_accuracy']:.1%}",
    )
    page_column.metric(
        "关键页命中率",
        f"{summary['retrieval_page_hit_rate']:.1%}",
    )

    metric_column, escalation_column, refusal_column = st.columns(3)
    metric_column.metric(
        "指标计算准确率",
        f"{summary['metric_accuracy']:.1%}",
    )
    escalation_column.metric(
        "动态升级准确率",
        f"{summary['escalation_accuracy']:.1%}",
    )
    refusal_column.metric(
        "安全拒答准确率",
        f"{summary['safe_refusal_accuracy']:.1%}",
    )

    failed_results = [
        result for result in results if not result["passed"]
    ]
    if not failed_results:
        st.success("所有人工定义的基准案例均已通过。")
        return

    st.warning(
        f"仍有 {len(failed_results)} 个基准案例存在已知缺口。"
        "系统会保留这些结果，以便衡量后续检索改动。"
    )
    with st.expander("已知质量缺口"):
        for result in failed_results:
            st.markdown(
                f"**{result['case_id']}: {result['question']}**"
            )
            for check in result["checks"]:
                if check["passed"]:
                    continue
                st.markdown(
                    f"- {check['name']}：预期 "
                    f"`{check['expected']}`，实际 "
                    f"`{check['actual']}`"
                )
            st.caption(result["notes"])


def show_verification_result(result: VerificationResult) -> None:
    """Display the deterministic output audit in a compact, readable form."""
    st.markdown("#### Verifier Agent 输出审计")
    if result["status"] == "rejected":
        st.error(result["summary"])
    elif result["status"] == "approved_with_caveats":
        st.warning(result["summary"])
    else:
        st.success(result["summary"])

    for check in result["checks"]:
        symbol = "✅" if check["passed"] else "❌"
        st.markdown(f"{symbol} **{check['name']}**")
        st.caption(check["detail"])
    st.caption(result["limitation"])


def show_llm_analyst_result(result: LLMAnalystRun) -> None:
    """Display only LLM output that passed all local guardrails."""
    st.markdown("#### LLM Agent 综合分析")
    if result["status"] == "disabled":
        st.info(result["summary"])
        return
    if result["status"] == "fallback":
        st.warning(result["summary"])
        if result["checks"]:
            with st.expander("LLM 安全保护检查"):
                for check in result["checks"]:
                    symbol = "✅" if check["passed"] else "❌"
                    st.markdown(f"{symbol} **{check['name']}**")
                    st.caption(check["detail"])
        return

    analysis = result["analysis"]
    assert analysis is not None
    st.success(result["summary"])
    st.caption(
        f"模型：{result['model']}。模型只接收已验证证据和 Python "
        "确定性计算结果，不会接收 API 密钥。"
    )
    st.info(analysis.conclusion)
    st.markdown("**综合证据要点**")
    for point in analysis.evidence_points:
        st.markdown(
            f"- {point.claim} **[PDF 第 {point.source_page} 页]**"
        )
        st.caption(f"原文依据：“{point.supporting_excerpt}”")
    st.caption(f"分析局限：{analysis.limitation}")

    with st.expander("LLM 安全保护检查"):
        for check in result["checks"]:
            symbol = "✅" if check["passed"] else "❌"
            st.markdown(f"{symbol} **{check['name']}**")
            st.caption(check["detail"])


def explain_net_profit_margin(margin: float) -> str:
    """Return a factual, rule-based explanation of the calculated margin."""
    if margin > 0:
        return (
            "公司实现盈利。每获得 1 元营业收入，约形成 "
            f"{margin:.1%} 的净利润。"
        )
    if margin < 0:
        return (
            "公司出现亏损，净亏损约相当于营业收入的 "
            f"{abs(margin):.1%}。"
        )
    return "公司处于盈亏平衡状态：净利润率为 0%。"


def explain_revenue_growth(growth: float) -> str:
    """Return a factual, rule-based explanation of revenue growth."""
    if growth > 0:
        return f"营业收入较上期增长 {growth:.1%}。"
    if growth < 0:
        return f"营业收入较上期下降 {abs(growth):.1%}。"
    return "营业收入与上期持平。"


def explain_current_ratio(ratio: float) -> str:
    """Return a factual, rule-based explanation of the current ratio."""
    if ratio > 1:
        return (
            f"流动资产是流动负债的 {ratio:.2f} 倍，"
            "报告日流动资产高于流动负债。"
        )
    if ratio < 1:
        return (
            f"流动资产是流动负债的 {ratio:.2f} 倍，"
            "报告日流动资产低于流动负债。"
        )
    return "报告日流动资产与流动负债相等。"


def explain_liabilities_to_assets_ratio(ratio: float) -> str:
    """Return a factual explanation of the liabilities-to-assets ratio."""
    if ratio > 1:
        return (
            f"总负债是总资产的 {ratio:.2f} 倍，"
            "高于企业报告的资产基础。"
        )
    return f"总负债约占总资产的 {ratio:.1%}。"


@st.cache_data(show_spinner=False)
def read_uploaded_pdf(pdf_bytes: bytes) -> list[ExtractedPage]:
    """Cache page extraction so the same upload is not processed repeatedly."""
    return extract_pdf_pages(pdf_bytes)


@st.cache_data(show_spinner=False)
def build_search_chunks(
    pages: list[ExtractedPage],
) -> list[ReportChunk]:
    """Cache page-preserving chunks used by the evidence search."""
    return chunk_report_pages(pages)


def apply_product_theme() -> None:
    """Apply a restrained finance-and-technology visual system."""
    st.markdown(
        """
        <style>
        :root {
            --wfz-navy: #0a1930;
            --wfz-blue: #163d67;
            --wfz-teal: #0b8f8c;
            --wfz-gold: #c8a45d;
            --wfz-ink: #132238;
            --wfz-muted: #607087;
            --wfz-line: rgba(22, 61, 103, 0.12);
        }

        .stApp {
            background:
                radial-gradient(
                    circle at 12% 0%,
                    rgba(11, 143, 140, 0.09),
                    transparent 28rem
                ),
                radial-gradient(
                    circle at 92% 8%,
                    rgba(200, 164, 93, 0.11),
                    transparent 24rem
                ),
                #f6f8fb;
            color: var(--wfz-ink);
        }

        [data-testid="stHeader"] {
            background: transparent;
        }

        [data-testid="stToolbar"],
        #MainMenu,
        footer {
            visibility: hidden;
            height: 0;
        }

        .block-container {
            max-width: 1180px;
            padding-top: 1.6rem;
            padding-bottom: 4rem;
        }

        .wfz-hero {
            position: relative;
            overflow: hidden;
            min-height: 420px;
            margin-bottom: 2.4rem;
            padding: 3.2rem 3.5rem;
            border: 1px solid rgba(255, 255, 255, 0.18);
            border-radius: 28px;
            background:
                linear-gradient(
                    125deg,
                    rgba(5, 20, 40, 0.98) 0%,
                    rgba(12, 48, 77, 0.97) 58%,
                    rgba(10, 91, 91, 0.94) 100%
                );
            box-shadow:
                0 30px 70px rgba(9, 30, 54, 0.20),
                inset 0 1px 0 rgba(255, 255, 255, 0.10);
            color: white;
        }

        .wfz-hero::before {
            content: "";
            position: absolute;
            width: 360px;
            height: 360px;
            top: -180px;
            right: -80px;
            border: 1px solid rgba(255, 255, 255, 0.16);
            border-radius: 50%;
            box-shadow:
                0 0 0 55px rgba(255, 255, 255, 0.025),
                0 0 0 110px rgba(255, 255, 255, 0.018);
        }

        .wfz-kicker {
            position: relative;
            z-index: 1;
            margin-bottom: 1.25rem;
            color: #91ded7;
            font-size: 0.76rem;
            font-weight: 750;
            letter-spacing: 0.18em;
        }

        .wfz-title {
            position: relative;
            z-index: 1;
            max-width: 780px;
            margin: 0;
            color: #ffffff;
            font-family:
                "Avenir Next", "Helvetica Neue", Arial, sans-serif;
            font-size: clamp(2.6rem, 6vw, 5.1rem);
            font-weight: 720;
            letter-spacing: -0.055em;
            line-height: 0.98;
        }

        .wfz-title span {
            color: #cdece9;
        }

        .wfz-subtitle {
            position: relative;
            z-index: 1;
            max-width: 680px;
            margin: 1.55rem 0 1.8rem;
            color: rgba(255, 255, 255, 0.76);
            font-size: 1.02rem;
            line-height: 1.7;
        }

        .wfz-badges {
            position: relative;
            z-index: 1;
            display: flex;
            flex-wrap: wrap;
            gap: 0.6rem;
            margin-bottom: 2rem;
        }

        .wfz-badge {
            padding: 0.5rem 0.82rem;
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.08);
            color: rgba(255, 255, 255, 0.90);
            font-size: 0.76rem;
            font-weight: 600;
            backdrop-filter: blur(8px);
        }

        .wfz-author {
            position: relative;
            z-index: 1;
            display: inline-flex;
            align-items: center;
            gap: 0.8rem;
            padding: 0.72rem 1rem 0.72rem 0.74rem;
            border: 1px solid rgba(255, 255, 255, 0.17);
            border-radius: 16px;
            background: rgba(0, 0, 0, 0.13);
        }

        .wfz-monogram {
            display: grid;
            width: 42px;
            height: 42px;
            place-items: center;
            border-radius: 12px;
            background: linear-gradient(145deg, #d6b774, #a98542);
            color: #10243a;
            font-size: 0.78rem;
            font-weight: 800;
            letter-spacing: 0.04em;
        }

        .wfz-author-label {
            display: block;
            margin-bottom: 0.18rem;
            color: rgba(255, 255, 255, 0.52);
            font-size: 0.62rem;
            font-weight: 700;
            letter-spacing: 0.12em;
        }

        .wfz-author-name {
            color: white;
            font-size: 0.92rem;
            font-weight: 680;
            letter-spacing: 0.01em;
        }

        .wfz-section-label {
            display: inline-block;
            margin: 0.5rem 0 0.3rem;
            color: var(--wfz-teal);
            font-size: 0.7rem;
            font-weight: 800;
            letter-spacing: 0.15em;
        }

        h1, h2, h3, h4 {
            color: var(--wfz-navy);
            font-family:
                "Avenir Next", "Helvetica Neue", Arial, sans-serif;
            letter-spacing: -0.025em;
        }

        h2, h3 {
            padding-top: 0.35rem;
        }

        p, label, [data-testid="stCaptionContainer"] {
            color: var(--wfz-muted);
        }

        [data-testid="stForm"],
        [data-testid="stFileUploader"] {
            border: 1px solid var(--wfz-line);
            border-radius: 20px;
            background: rgba(255, 255, 255, 0.78);
            box-shadow: 0 12px 35px rgba(17, 49, 80, 0.06);
        }

        [data-testid="stForm"] {
            padding: 1.25rem;
        }

        [data-testid="stMetric"] {
            min-height: 128px;
            padding: 1.15rem 1.25rem;
            border: 1px solid var(--wfz-line);
            border-radius: 18px;
            background:
                linear-gradient(
                    145deg,
                    rgba(255, 255, 255, 0.98),
                    rgba(243, 248, 250, 0.92)
                );
            box-shadow: 0 12px 30px rgba(17, 49, 80, 0.07);
        }

        [data-testid="stMetricValue"] {
            color: var(--wfz-navy);
            font-weight: 720;
        }

        .stButton > button,
        .stDownloadButton > button,
        .stFormSubmitButton > button {
            min-height: 2.85rem;
            border: 0;
            border-radius: 12px;
            background: linear-gradient(
                105deg,
                var(--wfz-blue),
                var(--wfz-teal)
            );
            box-shadow: 0 9px 22px rgba(11, 101, 111, 0.18);
            color: white;
            font-weight: 700;
            transition:
                transform 160ms ease,
                box-shadow 160ms ease;
        }

        .stButton > button *,
        .stDownloadButton > button *,
        .stFormSubmitButton > button * {
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
            text-shadow: 0 1px 1px rgba(5, 20, 40, 0.18);
        }

        .stButton > button:hover,
        .stDownloadButton > button:hover,
        .stFormSubmitButton > button:hover {
            border: 0;
            color: #ffffff !important;
            transform: translateY(-1px);
            box-shadow: 0 12px 26px rgba(11, 101, 111, 0.25);
        }

        .stButton > button:focus-visible,
        .stDownloadButton > button:focus-visible,
        .stFormSubmitButton > button:focus-visible {
            outline: 3px solid rgba(200, 164, 93, 0.72);
            outline-offset: 3px;
        }

        .stButton > button:disabled,
        .stDownloadButton > button:disabled,
        .stFormSubmitButton > button:disabled {
            opacity: 0.68;
        }

        [data-testid="stAlert"],
        [data-testid="stExpander"] {
            border-radius: 15px;
        }

        hr {
            margin: 2.6rem 0;
            border-color: var(--wfz-line);
        }

        .wfz-footer {
            margin-top: 4rem;
            padding: 1.35rem 1.55rem;
            border-top: 1px solid var(--wfz-line);
            color: var(--wfz-muted);
            font-size: 0.78rem;
            letter-spacing: 0.02em;
            text-align: center;
        }

        .wfz-footer strong {
            color: var(--wfz-navy);
        }

        @media (max-width: 720px) {
            .block-container {
                padding-top: 0.8rem;
                padding-left: 1rem;
                padding-right: 1rem;
            }

            .wfz-hero {
                min-height: auto;
                padding: 2rem 1.4rem;
                border-radius: 22px;
            }

            .wfz-title {
                font-size: 2.55rem;
            }

            .wfz-subtitle {
                font-size: 0.92rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def show_product_identity() -> None:
    """Render the portfolio brand and developer attribution."""
    st.markdown(
        """
        <section class="wfz-hero">
            <div class="wfz-kicker">
                WFZ FINANCIAL INTELLIGENCE · 国内求职演示版
            </div>
            <h1 class="wfz-title">
                中国上市公司<br><span>自主研究 Agent</span>
            </h1>
            <p class="wfz-subtitle">
                输入公司名称或股票代码，统一查看官方公告、历史 K 线、
                年报证据与 Agent 审计结果。Python 负责透明计算，
                原始链接和 PDF 页码保证结论可追溯。
            </p>
            <div class="wfz-badges">
                <span class="wfz-badge">中国上市公司</span>
                <span class="wfz-badge">官方动态墙</span>
                <span class="wfz-badge">K 线与风险指标</span>
                <span class="wfz-badge">PYTHON 数值验证</span>
                <span class="wfz-badge">PDF 页码溯源</span>
                <span class="wfz-badge">多 AGENT 审计轨迹</span>
                <span class="wfz-badge">不提供投资建议</span>
            </div>
            <div class="wfz-author">
                <div class="wfz-monogram">WFZ</div>
                <div>
                    <span class="wfz-author-label">
                        产品设计与研发 / DESIGNED &amp; DEVELOPED BY
                    </span>
                    <span class="wfz-author-name">
                        王方正 · Durham University
                    </span>
                </div>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def show_chinese_user_guide() -> None:
    """Offer the companion Chinese guide inside the product."""
    with st.expander("📘 中文使用说明书与国内求职演示指南"):
        st.write(
            "说明书包含产品功能、操作步骤、三分钟面试演示流程、"
            "安全边界和常见问题。"
        )
        try:
            guide_text = CHINESE_USER_GUIDE_PATH.read_text(
                encoding="utf-8"
            )
        except OSError:
            st.warning("中文说明书暂时无法读取。")
            return

        st.download_button(
            "下载中文使用说明书（Markdown）",
            data=guide_text,
            file_name="WFZ_中国上市公司研究Agent_中文使用说明.md",
            mime="text/markdown",
            use_container_width=True,
        )


@st.cache_data(ttl=3600, show_spinner=False)
def load_a_share_directory() -> pd.DataFrame:
    """Cache the public company directory for one hour."""
    return fetch_company_directory()


@st.cache_data(ttl=3600, show_spinner=False)
def load_a_share_history(
    code: str,
    start_date_text: str,
    end_date_text: str,
    adjust: str,
) -> pd.DataFrame:
    """Cache one validated K-line request for one hour."""
    return fetch_market_history(
        code=code,
        start_date=date.fromisoformat(start_date_text),
        end_date=date.fromisoformat(end_date_text),
        adjust=adjust,
    )


@st.cache_data(ttl=3600, show_spinner=False)
def load_company_announcements(
    code: str,
    start_date_text: str,
    end_date_text: str,
    category: str = "",
) -> pd.DataFrame:
    """Cache official disclosure metadata for one hour."""
    return fetch_announcements(
        code=code,
        start_date=date.fromisoformat(start_date_text),
        end_date=date.fromisoformat(end_date_text),
        category=category,
    )


@st.cache_data(ttl=3600, show_spinner=False)
def load_official_annual_report(announcement_url: str) -> bytes:
    """Temporarily cache a validated official annual-report PDF."""
    return download_official_pdf(announcement_url)


def show_compact_page_header(
    section: str,
    title: str,
    description: str,
) -> None:
    """Render a consistent subpage heading without repeating the home hero."""
    st.markdown(
        f'<div class="wfz-section-label">{section}</div>',
        unsafe_allow_html=True,
    )
    st.title(title)
    st.write(description)


def show_product_footer() -> None:
    """Render the common developer attribution and product boundary."""
    st.markdown(
        """
        <div class="wfz-footer">
            <strong>WFZ 中国上市公司自主研究 Agent</strong> · 产品设计与研发：
            <strong>王方正 · Durham University</strong><br>
            以证据为核心的上市公司研究，用于教育、求职演示与作品集展示；
            不构成投资建议。
        </div>
        """,
        unsafe_allow_html=True,
    )


def _page_target(name: str) -> object | None:
    """Return a page object registered by the main navigation."""
    registry = st.session_state.get("_wfz_page_registry", {})
    return registry.get(name) if isinstance(registry, dict) else None


def _switch_page(name: str) -> None:
    """Navigate between function-backed Streamlit pages when available."""
    target = _page_target(name)
    if target is not None:
        st.switch_page(target)


def _store_selected_company(company: CompanyIdentity) -> None:
    """Keep one company identity across every research subpage."""
    st.session_state["selected_company"] = dict(company)


def _selected_company() -> CompanyIdentity | None:
    """Return the selected company if its stored shape is still valid."""
    stored = st.session_state.get("selected_company")
    if not isinstance(stored, dict):
        return None
    required = {
        "code",
        "name",
        "exchange",
        "exchange_name",
        "canonical_code",
    }
    if not required.issubset(stored):
        return None
    return stored  # type: ignore[return-value]


def _render_company_search(
    *,
    key_prefix: str,
    navigate_on_success: bool,
) -> CompanyIdentity | None:
    """Resolve a company code/name with a live directory and safe fallback."""
    matches_key = f"{key_prefix}_company_matches"
    with st.form(f"{key_prefix}_company_search_form"):
        query = st.text_input(
            "输入A股公司名称或6位股票代码",
            placeholder="例如：贵州茅台、600519、宁德时代、300750",
            key=f"{key_prefix}_company_query",
        )
        submitted = st.form_submit_button(
            "开始研究",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        directory: pd.DataFrame | None
        try:
            with st.spinner("正在核验上市公司身份……"):
                directory = load_a_share_directory()
        except (DataSourceError, ValueError):
            directory = None
            st.info(
                "实时公司目录暂时不可用，系统正在使用本地核验名单；"
                "直接输入6位股票代码仍可继续。"
            )

        matches = resolve_company(query, directory)
        st.session_state[matches_key] = matches
        if not matches:
            st.warning(
                "暂时没有找到匹配的沪、深或北交所上市公司。"
                "请检查名称，或直接输入6位股票代码。"
            )
            return None

        if len(matches) == 1:
            company = matches[0]
            _store_selected_company(company)
            if navigate_on_success:
                _switch_page("company")
            return company

    matches = st.session_state.get(matches_key, [])
    if isinstance(matches, list) and len(matches) > 1:
        options = {
            (
                f"{item['name']}｜{item['canonical_code']}｜"
                f"{item['exchange_name']}"
            ): item
            for item in matches
        }
        selection = st.selectbox(
            "找到多个结果，请确认研究对象",
            options=list(options),
            key=f"{key_prefix}_company_choice",
        )
        if st.button(
            "确认公司",
            type="primary",
            use_container_width=True,
            key=f"{key_prefix}_confirm_company",
        ):
            company = options[selection]
            _store_selected_company(company)
            if navigate_on_success:
                _switch_page("company")
            return company
    return _selected_company()


def _show_company_banner(company: CompanyIdentity) -> None:
    """Keep company, code, exchange, and research scope visible."""
    st.info(
        f"当前研究对象：**{company['name']}**｜"
        f"**{company['canonical_code']}**｜"
        f"{company['exchange_name']}。"
    )
    if company["name"] == "待核验公司":
        st.warning(
            "当前只根据6位代码识别了交易所，公司名称尚未通过实时目录核验。"
            "请在数据源恢复后重新搜索，核验前不要据此形成结论。"
        )
    if st.button(
        "更换研究公司",
        key=f"change_company_{company['canonical_code']}",
    ):
        st.session_state.pop("selected_company", None)
        _switch_page("home")


def _format_percent(value: float | None) -> str:
    """Format an optional ratio without disguising missing evidence as zero."""
    return "数据不足" if value is None else f"{value:.1%}"


def _show_market_activity_evidence(
    activity: MarketActivityEvidence,
) -> None:
    """Render activity signals separately from investment interpretation."""
    st.subheader("市场活跃度证据")
    st.caption(
        "这里回答“当天交易是否活跃”，不把放量或涨停候选解释成利好、"
        "利空或买卖信号。"
    )
    columns = st.columns(4)
    columns[0].metric(
        "最新日涨跌幅",
        _format_percent(activity["daily_return"]),
    )
    volume_ratio = activity["volume_ratio_20d"]
    columns[1].metric(
        "成交量 / 前20日中位数",
        "数据不足" if volume_ratio is None else f"{volume_ratio:.2f}倍",
        activity["volume_signal"],
        delta_color="off",
    )
    columns[2].metric(
        "普通换手率",
        _format_percent(activity["turnover"]),
    )
    columns[3].metric(
        "涨停状态",
        activity["limit_up_status"],
        f"规则参考 {activity['limit_up_reference']:.0%}",
        delta_color="off",
    )
    st.caption(
        f"普通换手率：{activity['turnover_status']}。"
        f"有效换手率：{activity['effective_turnover_status']}。"
    )
    with st.expander("查看涨停候选与有效换手率的严谨边界"):
        st.write(activity["limit_up_note"])
        st.write(
            "普通换手率使用公开行情源直接提供的字段；"
            "“有效换手率”需要可核验的时点自由流通股本作为分母。"
            "当前缺少该证据时，系统明确显示缺失，不使用普通换手率冒充。"
        )
        st.markdown(
            "规则依据（截至2026-07-30）："
            "[上交所2026年交易规则]"
            "(https://www.sse.com.cn/lawandrules/sselawsrules2025/"
            "stocks/exchange/c/c_20260424_10816482.shtml)｜"
            "[深交所主板规则说明]"
            "(https://investor.szse.cn/knowledge/qa/"
            "t20230306_599093.html)｜"
            "[北交所2026年交易规则]"
            "(https://www.bse.cn/jygl_list/200028217.html)"
        )


def _load_company_research_data(
    company: CompanyIdentity,
) -> tuple[pd.DataFrame | None, MarketMetrics | None, pd.DataFrame | None]:
    """Load market history and announcements independently and safely."""
    end_date = date.today()
    market_start = end_date - timedelta(days=550)
    # Eighteen months keeps the latest full annual report in scope even late
    # in the calendar year, while the wall still shows only the newest items.
    announcement_start = end_date - timedelta(days=550)
    market_frame: pd.DataFrame | None = None
    metrics: MarketMetrics | None = None
    announcements: pd.DataFrame | None = None

    try:
        market_frame = load_a_share_history(
            company["code"],
            market_start.isoformat(),
            end_date.isoformat(),
            "qfq",
        )
        if not market_frame.empty:
            metrics = calculate_market_metrics(market_frame)
    except (DataSourceError, ValueError):
        pass

    try:
        announcements = load_company_announcements(
            company["code"],
            announcement_start.isoformat(),
            end_date.isoformat(),
        )
    except (DataSourceError, ValueError):
        pass
    return market_frame, metrics, announcements


def render_home_page() -> None:
    """Render the single-entry home page for the research product."""
    apply_product_theme()
    show_product_identity()
    show_chinese_user_guide()

    st.markdown(
        '<div class="wfz-section-label">'
        "开始研究 · START RESEARCH"
        "</div>",
        unsafe_allow_html=True,
    )
    st.header("输入公司名称或股票代码")
    st.write(
        "系统将核验上市公司身份，并逐步连接官方披露、年报证据与"
        "历史市场数据。普通功能不依赖付费AI额度。"
    )
    _render_company_search(
        key_prefix="home",
        navigate_on_success=True,
    )

    st.divider()
    columns = st.columns(3)
    with columns[0]:
        with st.container(border=True):
            st.subheader("官方披露优先")
            st.write(
                "以巨潮资讯和交易所公开信息为主要来源，保留公告日期、"
                "标题和原始链接。"
            )
    with columns[1]:
        with st.container(border=True):
            st.subheader("Python透明计算")
            st.write(
                "财务比率、收益率、波动率和最大回撤均由确定性代码计算，"
                "不会交给AI猜测。"
            )
    with columns[2]:
        with st.container(border=True):
            st.subheader("证据可追溯")
            st.write(
                "研究结果保留年报页码、数据来源和验证状态，"
                "并明确展示证据不足之处。"
            )

    st.markdown(
        '<div class="wfz-section-label">'
        "研究流程 · RESEARCH WORKFLOW"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "**识别公司 → 获取官方资料 → 核验数据 → Python计算 → "
        "Agent质疑 → 结合市场表现 → 生成研究结果**"
    )
    st.caption(
        "第一阶段覆盖中国沪、深、北交所上市公司；"
        "本产品不预测短期涨跌，也不提供买卖建议。"
    )
    show_product_footer()


def _show_announcement_wall(announcements: pd.DataFrame) -> None:
    """Render a concise, source-linked official disclosure wall."""
    st.subheader("最新官方动态")
    st.caption(
        "系统按需同步公开公告并最多缓存1小时，不需要开发者每天更新；"
        "“关注程度”表示需要阅读的优先级，不代表利好或利空。"
    )
    if announcements.empty:
        st.info("查询范围内暂未取得可展示的官方公告。")
        return

    category_filter = st.multiselect(
        "筛选公告类别",
        options=sorted(announcements["category"].unique()),
        placeholder="默认显示全部类别",
    )
    display_frame = announcements
    if category_filter:
        display_frame = display_frame.loc[
            display_frame["category"].isin(category_filter)
        ]

    for item in display_frame.head(12).itertuples(index=False):
        with st.container(border=True):
            metadata_column, link_column = st.columns([5, 1])
            with metadata_column:
                st.markdown(f"**{item.title}**")
                st.caption(
                    f"{item.date.isoformat()}｜{item.category}｜"
                    f"关注程度：{item.attention}｜来源：巨潮资讯"
                )
            with link_column:
                st.markdown(
                    f"[查看原文 ↗]({item.url})",
                )


def render_company_research_page() -> None:
    """Render company overview, market metrics, and official dynamics."""
    apply_product_theme()
    show_compact_page_header(
        "01 / 公司研究中心 · COMPANY RESEARCH",
        "公司研究中心",
        "一个页面查看上市公司身份、市场概览、官方动态和最新年报入口。",
    )
    company = _selected_company()
    if company is None:
        st.warning("请先选择研究对象。")
        _render_company_search(
            key_prefix="company",
            navigate_on_success=False,
        )
        show_product_footer()
        return

    _show_company_banner(company)
    with st.spinner("正在同步公开市场数据与最新公告……"):
        market_frame, metrics, announcements = _load_company_research_data(
            company
        )

    st.subheader("市场概览")
    if metrics is None:
        st.warning(
            "历史行情数据源暂时不可用。年报分析和手工上传功能仍可使用。"
        )
    else:
        columns = st.columns(4)
        columns[0].metric(
            "最新收盘价",
            f"¥{metrics['latest_close']:,.2f}",
            _format_percent(metrics["daily_change"]),
        )
        columns[1].metric(
            "近20交易日",
            _format_percent(metrics["return_20d"]),
        )
        columns[2].metric(
            "年化历史波动率",
            _format_percent(metrics["annualised_volatility"]),
        )
        columns[3].metric(
            "区间最大回撤",
            _format_percent(metrics["max_drawdown"]),
        )
        st.caption(
            f"行情最后日期：{metrics['latest_date']}；前复权日线；"
            f"来源：{market_frame.attrs.get('source', '公开行情适配器')}；"
            "所有指标由Python计算。历史表现不代表未来结果。"
        )

    action_columns = st.columns(3)
    if action_columns[0].button(
        "查看完整K线与市场表现",
        use_container_width=True,
        type="primary",
    ):
        _switch_page("market")
    if action_columns[1].button(
        "进入 Historical Lens",
        use_container_width=True,
    ):
        _switch_page("historical")
    if action_columns[2].button(
        "进入年报与证据分析",
        use_container_width=True,
    ):
        _switch_page("annual")

    st.divider()
    if announcements is None:
        st.warning(
            "官方公告源暂时无法访问。系统不会使用未经核验的内容替代。"
        )
    else:
        latest_report = select_latest_annual_report(announcements)
        if latest_report is not None:
            with st.container(border=True):
                st.markdown("#### 最近完整年度报告")
                st.write(latest_report["title"])
                st.caption(
                    f"公告日期：{latest_report['date'].isoformat()}｜"
                    "来源：巨潮资讯"
                )
                st.link_button(
                    "查看官方年度报告",
                    str(latest_report["url"]),
                )
        _show_announcement_wall(announcements)
    show_product_footer()


def _build_kline_figure(frame: pd.DataFrame, company: CompanyIdentity) -> object:
    """Build a Chinese-market candlestick and volume figure."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    prepared = add_moving_averages(frame)
    figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.72, 0.28],
    )
    figure.add_trace(
        go.Candlestick(
            x=prepared["date"],
            open=prepared["open"],
            high=prepared["high"],
            low=prepared["low"],
            close=prepared["close"],
            name="日K",
            increasing_line_color="#d94841",
            decreasing_line_color="#159c74",
        ),
        row=1,
        col=1,
    )
    average_colours = {
        5: "#c28a24",
        20: "#3577a8",
        60: "#7c5aa6",
    }
    for window, colour in average_colours.items():
        figure.add_trace(
            go.Scatter(
                x=prepared["date"],
                y=prepared[f"ma_{window}"],
                mode="lines",
                line={"width": 1.4, "color": colour},
                name=f"MA{window}",
            ),
            row=1,
            col=1,
        )

    volume_colours = [
        "#d94841" if close >= open_price else "#159c74"
        for open_price, close in zip(
            prepared["open"],
            prepared["close"],
            strict=True,
        )
    ]
    figure.add_trace(
        go.Bar(
            x=prepared["date"],
            y=prepared["volume"],
            marker_color=volume_colours,
            name="成交量",
        ),
        row=2,
        col=1,
    )
    figure.update_layout(
        title=f"{company['name']}｜{company['canonical_code']}",
        height=680,
        margin={"l": 20, "r": 20, "t": 58, "b": 20},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,0.72)",
        hovermode="x unified",
        legend={"orientation": "h", "y": 1.04, "x": 0},
        xaxis_rangeslider_visible=False,
    )
    figure.update_yaxes(title_text="价格（元）", row=1, col=1)
    figure.update_yaxes(title_text="成交量", row=2, col=1)
    return figure


def render_market_page() -> None:
    """Render validated daily K-line data and deterministic risk metrics."""
    apply_product_theme()
    show_compact_page_header(
        "02 / K线与市场表现 · MARKET EVIDENCE",
        "K线与市场表现",
        "用日线、成交量和透明统计指标观察历史市场表现，不预测未来涨跌。",
    )
    company = _selected_company()
    if company is None:
        st.warning("请先在首页选择一家中国上市公司。")
        _render_company_search(
            key_prefix="market",
            navigate_on_success=False,
        )
        show_product_footer()
        return

    _show_company_banner(company)
    control_columns = st.columns(2)
    period_label = control_columns[0].selectbox(
        "时间范围",
        options=["近1年", "近3年", "近5年"],
        index=1,
    )
    adjustment_label = control_columns[1].selectbox(
        "价格口径",
        options=["前复权", "不复权", "后复权"],
        index=0,
        help=(
            "前复权适合观察连续历史趋势；不复权显示当时真实成交价格；"
            "不同口径不能混合比较。"
        ),
    )
    period_days = {
        "近1年": 370,
        "近3年": 1_100,
        "近5年": 1_840,
    }
    adjustment = {
        "前复权": "qfq",
        "不复权": "",
        "后复权": "hfq",
    }
    end_date = date.today()
    start_date = end_date - timedelta(days=period_days[period_label])

    try:
        with st.spinner("正在读取并校验历史日线……"):
            market_frame = load_a_share_history(
                company["code"],
                start_date.isoformat(),
                end_date.isoformat(),
                adjustment[adjustment_label],
            )
            metrics = calculate_market_metrics(market_frame)
            activity = calculate_market_activity(market_frame, company)
    except (DataSourceError, ValueError) as error:
        st.error(str(error))
        st.info(
            "公开数据源恢复后可直接重试；该故障不会影响年报PDF分析。"
        )
        show_product_footer()
        return

    columns = st.columns(5)
    columns[0].metric("最新收盘", f"¥{metrics['latest_close']:,.2f}")
    columns[1].metric("20日收益率", _format_percent(metrics["return_20d"]))
    columns[2].metric("60日收益率", _format_percent(metrics["return_60d"]))
    columns[3].metric(
        "年化波动率",
        _format_percent(metrics["annualised_volatility"]),
    )
    columns[4].metric(
        "最大回撤",
        _format_percent(metrics["max_drawdown"]),
    )

    _show_market_activity_evidence(activity)

    figure = _build_kline_figure(market_frame, company)
    st.plotly_chart(
        figure,
        use_container_width=True,
        config={"displaylogo": False},
    )
    st.caption(
        f"数据截至 {metrics['latest_date']}；{adjustment_label}日线；"
        f"有效观测 {metrics['observations']} 个交易日。"
        f"来源：{market_frame.attrs.get('source', '公开行情适配器')}。"
        "红色表示收盘不低于开盘，绿色表示收盘低于开盘。"
    )
    st.warning(
        "K线和历史统计只描述已经发生的市场表现，不能单独证明公司价值，"
        "也不构成买入、卖出或持有建议。"
    )
    show_product_footer()


def _announcement_evidence_records(
    announcements: pd.DataFrame,
) -> list[EvidenceRecord]:
    """Convert validated announcements to the shared evidence time schema."""
    records: list[EvidenceRecord] = []
    for item in announcements.itertuples(index=False):
        source_url = str(item.url)
        records.append(
            {
                "source_id": source_url,
                "source_type": str(item.category),
                "title": str(item.title),
                "published_date": item.date,
                "period_end": None,
                "source_url": source_url,
                "page_number": None,
                "evidence_grade": "A",
                "verification_status": "verified",
            }
        )
    return records


def render_historical_lens_page() -> None:
    """Render a point-in-time research view without look-ahead information."""
    apply_product_theme()
    show_compact_page_header(
        "03 / 历史回看 · HISTORICAL LENS",
        "Historical Lens｜回到当时再研究",
        "冻结历史信息截止线，先查看当时已经公开的证据，"
        "再单独揭示后来1、3、6个月的市场表现。",
    )
    company = _selected_company()
    if company is None:
        # The verified offline identity keeps the flagship demonstration usable
        # when the live company directory is temporarily unavailable.
        company = resolve_company("600519")[0]
        _store_selected_company(company)
        st.info("尚未选择公司，已载入首个演示对象：贵州茅台。")

    _show_company_banner(company)
    st.info(
        "时间隔离规则：只有发布日期不晚于所选日期的信息，"
        "才允许进入“当时已知”。后来行情在点击前不会显示。"
    )

    today = date.today()
    default_date = today - timedelta(days=365)
    selected_event = None
    if company["code"] == "600519":
        try:
            flagship_events = load_moutai_flagship_events()
        except ValueError:
            flagship_events = []
            st.warning("已核验的重要日期暂时无法读取，可继续自由选择日期。")

        if flagship_events:
            event_options = {"自由选择日期": None}
            for event in flagship_events:
                label = (
                    f"{event['event_date'].isoformat()}｜"
                    f"{event['title']}"
                )
                event_options[label] = event
            event_label = st.selectbox(
                "快速选择已核验的重要日期",
                options=list(event_options),
                index=len(event_options) - 1,
                help=(
                    "这些日期只提供官方事件入口和时间锚点，"
                    "不会预设事件对股价的影响。"
                ),
            )
            selected_event = event_options[event_label]
            if selected_event is not None:
                default_date = selected_event["event_date"]

    date_key_suffix = (
        selected_event["event_id"]
        if selected_event is not None
        else "custom"
    )
    selected_date = st.date_input(
        "选择历史研究截止日",
        value=default_date,
        min_value=today - timedelta(days=365 * 5),
        max_value=today,
        key=f"historical_date_{company['code']}_{date_key_suffix}",
        help=(
            "若所选日期不是交易日，系统会使用该日期之前最近一个交易日，"
            "并同时显示两个日期。"
        ),
    )
    if isinstance(selected_date, tuple):
        selected_date = selected_date[0]

    if selected_event is not None:
        with st.container(border=True):
            st.markdown(f"#### 已核验重要时点｜{selected_event['title']}")
            st.caption(
                f"事件日期：{selected_event['event_date'].isoformat()}｜"
                f"公开日期：{selected_event['published_date'].isoformat()}｜"
                f"{selected_event['category']}｜证据等级 "
                f"{selected_event['evidence_grade']}"
            )
            st.write(selected_event["why_important"])
            st.link_button(
                "查看该时点的官方原始证据",
                selected_event["source_url"],
            )

    history_start = selected_date - timedelta(days=550)
    history_end = min(today, selected_date + timedelta(days=250))
    try:
        with st.spinner("正在建立历史信息快照……"):
            # Unadjusted prices prevent today's adjustment factor from leaking
            # later corporate actions into an earlier point-in-time view.
            market_frame = load_a_share_history(
                company["code"],
                history_start.isoformat(),
                history_end.isoformat(),
                "",
            )
            market_source = market_frame.attrs.get(
                "source",
                "公开行情适配器",
            )
            snapshot = calculate_historical_snapshot(
                market_frame,
                selected_date,
                source=str(market_source),
                adjustment="不复权",
            )
    except (DataSourceError, ValueError) as error:
        st.error(str(error))
        st.info(
            "公开行情源恢复后可直接重试。系统不会用今天的数据"
            "替代所选历史日期。"
        )
        show_product_footer()
        return

    st.subheader("当时的市场状态")
    first_row = st.columns(4)
    first_row[0].metric(
        "当时收盘价",
        f"¥{snapshot['latest_close']:,.2f}",
    )
    first_row[1].metric(
        "当日成交量",
        f"{snapshot['volume']:,.0f}",
    )
    first_row[2].metric(
        "当日换手率",
        _format_percent(snapshot["turnover"]),
    )
    first_row[3].metric(
        "近20交易日",
        _format_percent(snapshot["return_20d"]),
    )
    second_row = st.columns(4)
    second_row[0].metric(
        "近60交易日",
        _format_percent(snapshot["return_60d"]),
    )
    second_row[1].metric(
        "近250交易日",
        _format_percent(snapshot["return_250d"]),
    )
    second_row[2].metric(
        "年化历史波动率",
        _format_percent(snapshot["annualised_volatility"]),
    )
    second_row[3].metric(
        "近250日最大回撤",
        _format_percent(snapshot["max_drawdown"]),
    )
    st.caption(
        f"用户选择：{snapshot['requested_date']}｜实际采用交易日："
        f"{snapshot['effective_market_date']}｜{snapshot['adjustment']}日线｜"
        f"最多使用此前250个交易日计算｜来源：{snapshot['source']}。"
    )

    historical_chart_frame = slice_market_as_of(
        market_frame,
        selected_date,
    ).tail(180)
    figure = _build_kline_figure(historical_chart_frame, company)
    st.plotly_chart(
        figure,
        use_container_width=True,
        config={"displaylogo": False},
    )
    st.caption(
        "图表在历史截止线处结束，不包含截止日之后的价格。"
        "Historical Lens 默认使用不复权价格，避免后来复权因子进入过去。"
    )

    st.divider()
    st.subheader("当时已经公开的官方证据")
    announcement_start = selected_date - timedelta(days=550)
    announcement_end = min(today, selected_date + timedelta(days=180))
    try:
        announcements = load_company_announcements(
            company["code"],
            announcement_start.isoformat(),
            announcement_end.isoformat(),
        )
    except (DataSourceError, ValueError):
        announcements = None

    if announcements is None:
        st.warning(
            "官方公告源暂时不可访问。市场快照仍然有效，"
            "公告证据不会由其他未经核验的内容替代。"
        )
    else:
        evidence_result = filter_evidence_as_of(
            _announcement_evidence_records(announcements),
            selected_date,
        )
        accepted = evidence_result["accepted"]
        if not accepted:
            st.info("当前查询范围内，没有取得截止日前可展示的官方公告。")
        for record in accepted[:8]:
            with st.container(border=True):
                text_column, link_column = st.columns([5, 1])
                with text_column:
                    st.markdown(f"**{record['title']}**")
                    published = record["published_date"]
                    published_text = (
                        published.isoformat()
                        if isinstance(published, date)
                        else str(published)
                    )
                    st.caption(
                        f"{published_text}｜{record['source_type']}｜"
                        "证据等级 A｜来源：巨潮资讯"
                    )
                with link_column:
                    st.markdown(
                        f"[查看原文 ↗]({record['source_url']})"
                    )

        known_announcements = announcements.loc[
            announcements["date"] <= selected_date
        ].copy()
        latest_known_report = select_latest_annual_report(
            known_announcements
        )
        if latest_known_report is not None:
            st.success(
                "当时最新可用的完整年度报告："
                f"{latest_known_report['title']}（发布于 "
                f"{latest_known_report['date'].isoformat()}）"
            )

        with st.expander("查看时间过滤审计"):
            st.write(
                f"取得证据 {evidence_result['input_count']} 条；"
                f"截止日内保留 {evidence_result['accepted_count']} 条；"
                f"因发布日期在截止日后排除 "
                f"{evidence_result['excluded_count']} 条。"
            )
            st.caption(
                "报告期早于截止日并不代表当时已经知道；"
                "系统以公开发布日期作为准入条件。"
            )

    st.divider()
    st.subheader("历史快照边界")
    st.markdown(
        "- **已确认：** 上方行情只使用历史截止日前的数据；\n"
        "- **可追溯：** 公告保留发布日期、类别和官方原文链接；\n"
        "- **仍未知：** 页面不把截止日后的价格或公告写进当时判断；\n"
        "- **解释限制：** 同期涨跌不能自动证明由某一公告造成。"
    )

    reveal_key = (
        f"historical_reveal_{company['code']}_{selected_date.isoformat()}"
    )
    if st.button(
        "揭示后来1、3、6个月的市场表现",
        type="primary",
        use_container_width=True,
        key=f"{reveal_key}_button",
    ):
        st.session_state[reveal_key] = True

    if st.session_state.get(reveal_key, False):
        outcomes = calculate_later_outcomes(
            market_frame,
            selected_date,
        )
        outcome_columns = st.columns(3)
        for column, outcome in zip(
            outcome_columns,
            outcomes,
            strict=True,
        ):
            with column:
                with st.container(border=True):
                    st.markdown(f"#### {outcome['label']}")
                    if outcome["status"] == "insufficient_future_data":
                        st.info("后来行情数据尚不足。")
                        continue
                    st.metric(
                        "区间收益",
                        _format_percent(outcome["return_since_base"]),
                    )
                    st.write(
                        f"结果日：{outcome['outcome_date']}  "
                        f"收盘：¥{outcome['outcome_close']:,.2f}"
                    )
                    st.caption(
                        "期间最高相对收益："
                        f"{_format_percent(outcome['maximum_gain'])}｜"
                        "期间最大回撤："
                        f"{_format_percent(outcome['maximum_drawdown'])}"
                    )
        st.warning(
            "后来表现只用于检验和复盘，不证明此前信息与涨跌存在因果关系，"
            "也不构成买入、卖出或持有建议。"
        )

    show_product_footer()


def render_methodology_page() -> None:
    """Explain source priority, calculation boundaries, and known limits."""
    apply_product_theme()
    show_compact_page_header(
        "05 / 方法与审计 · METHODOLOGY",
        "方法、证据与产品边界",
        "公开说明系统如何获取资料、计算指标、使用AI以及处理不确定性。",
    )
    with st.container(border=True):
        st.subheader("数据来源优先级")
        st.markdown(
            "1. 巨潮资讯、上交所、深交所、北交所等官方披露；\n"
            "2. 经过字段校验的公开历史行情；\n"
            "3. 公司投资者关系页面；\n"
            "4. 媒体新闻仅作为后续补充，不替代官方公告。"
        )
    with st.container(border=True):
        st.subheader("确定性计算与AI分工")
        st.write(
            "财务比率、收益率、波动率、最大回撤和移动平均线全部由"
            "Python计算。AI只允许基于已经核验的数字和原文证据生成解释，"
            "不得自行补充财务数字。"
        )
    with st.container(border=True):
        st.subheader("Historical Lens 时间隔离")
        st.write(
            "历史回看只允许使用发布日期不晚于所选截止日的证据。"
            "当时可见信息与后来1、3、6个月表现由不同函数计算，"
            "防止把未来数据带回过去。"
        )
    with st.container(border=True):
        st.subheader("已知限制")
        st.write(
            "公开数据源可能出现限速、暂时不可访问或字段变化；"
            "扫描版年报可能需要OCR；银行、保险与普通工业企业的报表结构"
            "不同，需要分行业验证。数据不足时系统应明确提示，而不是返回0。"
        )
    with st.container(border=True):
        st.subheader("产品用途")
        st.write(
            "本产品面向上市公司基本面研究、教育和求职作品集展示。"
            "所有结论均需结合原始公告、行业背景和个人风险承受能力判断，"
            "不提供个性化投资建议。"
        )
    show_chinese_user_guide()
    show_product_footer()


def render_annual_report_page() -> None:
    """Render the existing PDF evidence workflow as a dedicated subpage."""
    apply_product_theme()
    show_compact_page_header(
        "04 / 年报与证据 · ANNUAL REPORT",
        "年报与证据分析",
        "上传公开年度报告，按页提取文字、计算财务指标并生成可追溯答案。",
    )
    company = _selected_company()
    if company is not None:
        _show_company_banner(company)
    show_chinese_user_guide()

    automatic_report_bytes: bytes | None = None
    if company is not None:
        end_date = date.today()
        start_date = end_date - timedelta(days=550)
        latest_report = None
        try:
            announcements = load_company_announcements(
                company["code"],
                start_date.isoformat(),
                end_date.isoformat(),
            )
            latest_report = select_latest_annual_report(announcements)
        except (DataSourceError, ValueError):
            st.warning(
                "官方年报目录暂时无法同步，手工上传公开年报仍可正常使用。"
            )

        if latest_report is not None:
            with st.container(border=True):
                st.markdown("#### 已核验的最新完整年度报告")
                st.write(str(latest_report["title"]))
                st.caption(
                    f"公告日期：{latest_report['date'].isoformat()}｜"
                    "来源：巨潮资讯。自动载入为测试版，原文链接始终保留。"
                )
                report_columns = st.columns(2)
                report_columns[0].link_button(
                    "查看官方原文",
                    str(latest_report["url"]),
                    use_container_width=True,
                )
                auto_load_requested = report_columns[1].button(
                    "自动载入并分析",
                    type="primary",
                    use_container_width=True,
                    key=f"auto_load_{company['canonical_code']}",
                )

            if auto_load_requested:
                try:
                    with st.spinner("正在从官方披露地址临时载入年报……"):
                        automatic_report_bytes = load_official_annual_report(
                            str(latest_report["url"])
                        )
                except (DataSourceError, ValueError) as error:
                    st.error(str(error))
                    st.info("请打开官方原文下载PDF，再使用下方上传入口。")
                else:
                    report_title = str(latest_report["title"]).replace(
                        "/",
                        "_",
                    )
                    st.session_state["automatic_annual_report"] = {
                        "company_code": company["code"],
                        "name": f"{company['code']}_{report_title}.pdf",
                        "url": str(latest_report["url"]),
                    }
                    st.success(
                        "官方年报已临时载入，正在进入原有证据分析流程。"
                    )
        else:
            st.info(
                "当前没有找到可自动载入的完整年度报告，"
                "你仍可使用下方手工上传入口。"
            )

    st.markdown(
        (
            '<div class="wfz-section-label">'
            '01 / 年度报告智能解析 · DOCUMENT INTELLIGENCE'
            '</div>'
        ),
        unsafe_allow_html=True,
    )
    st.subheader("年度报告智能解析 / Annual Report")
    st.write(
        "上传年度报告 PDF 后，系统将按页提取文本并保留原始页码，"
        "便于后续分析引用和追溯证据。"
    )
    uploaded_report = st.file_uploader(
        "上传年度报告 PDF",
        type=["pdf"],
        help="请使用公开年度报告，不要上传个人或机密财务资料。",
    )

    automatic_report = st.session_state.get("automatic_annual_report")
    if (
        uploaded_report is None
        and company is not None
        and isinstance(automatic_report, dict)
        and automatic_report.get("company_code") == company["code"]
    ):
        try:
            if automatic_report_bytes is None:
                automatic_report_bytes = load_official_annual_report(
                    str(automatic_report["url"])
                )
        except (DataSourceError, ValueError) as error:
            st.error(str(error))
        else:
            in_memory_report = BytesIO(automatic_report_bytes)
            in_memory_report.name = str(automatic_report["name"])
            uploaded_report = in_memory_report
            st.caption(
                "当前使用服务器临时载入的官方年报；"
                "你也可以上传PDF来替换本次分析对象。"
            )

    if uploaded_report is not None:
        try:
            with st.spinner("正在读取年度报告……"):
                extracted_pages = read_uploaded_pdf(uploaded_report.getvalue())
        except ValueError as error:
            st.error(str(error))
        else:
            st.success(
                f"{uploaded_report.name} 读取成功，共 "
                f"{len(extracted_pages)} 页。"
            )
            extracted_figures = find_income_statement_figures(
                (
                    (page["page_number"], page["text"])
                    for page in extracted_pages
                )
            )
            balance_sheet_figures = find_balance_sheet_figures(
                (
                    (page["page_number"], page["text"])
                    for page in extracted_pages
                )
            )
            cash_flow_figures = find_cash_flow_figures(
                (
                    (page["page_number"], page["text"])
                    for page in extracted_pages
                )
            )
            default_page_index = (
                extracted_figures["page_number"] - 1
                if extracted_figures is not None
                else 0
            )
            selected_page_number = st.selectbox(
                "选择要预览的 PDF 页码",
                options=[page["page_number"] for page in extracted_pages],
                index=default_page_index,
            )
            selected_page = extracted_pages[selected_page_number - 1]
            page_text = selected_page["text"].strip()

            if page_text:
                st.text_area(
                    f"提取文本——PDF 第 {selected_page_number} 页",
                    value=page_text,
                    height=260,
                    disabled=True,
                )
            else:
                st.warning(
                    f"PDF 第 {selected_page_number} 页没有可提取文本，"
                    "该页可能是扫描图片。"
                )
            st.caption(
                f"证据来源：{uploaded_report.name}，"
                f"PDF 第 {selected_page_number} 页。"
            )

            st.subheader("基于证据向年报提问 / Evidence Q&A")
            st.write(
                "输入财务问题后，系统只使用检索到的年报原文生成答案，"
                "每条证据均保留对应 PDF 页码。"
            )
            use_llm_agent = st.toggle(
                "使用 LLM 综合分析（需要 OpenAI API 额度）",
                value=True,
                help=(
                    "只有本地 Verifier 通过证据检查后才会调用一次 API；"
                    "关闭后仍可使用全部本地检索、计算和验证功能。"
                ),
            )
            with st.form("report_evidence_search_form"):
                evidence_query = st.text_input(
                    "财务问题或主题",
                    placeholder=(
                        "示例：为什么经营现金流增加？"
                    ),
                )
                search_evidence = st.form_submit_button(
                    "生成带页码的证据答案",
                    type="primary",
                    use_container_width=True,
                )

            if search_evidence:
                if not evidence_query.strip():
                    st.warning("请先输入财务问题或主题。")
                else:
                    route_decision = route_question(evidence_query)
                    show_route_decision(route_decision)
                    report_chunks = build_search_chunks(extracted_pages)
                    initial_run = run_agent_workflow(
                        query=evidence_query,
                        chunks=report_chunks,
                        route=route_decision,
                        income_figures=extracted_figures,
                        balance_figures=balance_sheet_figures,
                    )
                    metric_result = initial_run["metric_result"]
                    if metric_result is not None:
                        show_metric_tool_result(metric_result)

                    escalation_decision = decide_adaptive_escalation(
                        current_route=route_decision,
                        answer=initial_run["answer"],
                        skeptical_review=initial_run["skeptical_review"],
                        verification=initial_run["verification"],
                        results=initial_run["results"],
                        metric_available=(
                            metric_result["is_available"]
                            if metric_result is not None
                            else None
                        ),
                    )
                    show_escalation_decision(escalation_decision)

                    if escalation_decision["escalated"]:
                        final_run = run_agent_workflow(
                            query=evidence_query,
                            chunks=report_chunks,
                            route=escalation_decision["route"],
                            income_figures=extracted_figures,
                            balance_figures=balance_sheet_figures,
                            existing_metric_result=metric_result,
                        )
                    else:
                        final_run = initial_run

                    show_agent_trace(
                        initial_run=initial_run,
                        final_run=final_run,
                        escalated=escalation_decision["escalated"],
                    )

                    evidence_results = final_run["results"]
                    answer_result = final_run["answer"]
                    skeptical_result = final_run["skeptical_review"]
                    verification_result = final_run["verification"]
                    llm_result: LLMAnalystRun | None = None
                    if use_llm_agent:
                        with st.spinner(
                            "LLM Agent 正在综合已验证证据……"
                        ):
                            llm_result = run_llm_analyst(
                                query=evidence_query,
                                answer=answer_result,
                                skeptical_review=skeptical_result,
                                verification=verification_result,
                                metric_result=final_run["metric_result"],
                            )

                    audit_record = build_agent_audit_record(
                        report_name=uploaded_report.name,
                        initial_route=route_decision,
                        escalation=escalation_decision,
                        initial_run=initial_run,
                        final_run=final_run,
                    )
                    audit_record["llm_analyst"] = (
                        serialise_llm_run(llm_result)
                        if llm_result is not None
                        else {
                            "status": "user_disabled",
                            "summary": (
                                "The user disabled the optional LLM "
                                "synthesis step."
                            ),
                        }
                    )
                    st.download_button(
                        "下载 Agent 审计记录（JSON）",
                        data=json.dumps(
                            audit_record,
                            ensure_ascii=False,
                            indent=2,
                        ),
                        file_name="agent_audit_trace.json",
                        mime="application/json",
                        use_container_width=True,
                    )

                    if not evidence_results:
                        st.warning(
                            "没有找到足够相关的年报证据。请尝试输入更具体的"
                            "财务术语。"
                        )
                    else:
                        assert answer_result is not None
                        assert skeptical_result is not None
                        assert verification_result is not None
                        st.markdown("#### 基于证据的回答")
                        if not answer_result["is_supported"]:
                            st.warning(answer_result["conclusion"])
                            st.caption(answer_result["limitation"])
                            show_verification_result(verification_result)
                            if llm_result is not None:
                                show_llm_analyst_result(llm_result)
                        else:
                            st.info(answer_result["conclusion"])
                            st.markdown("**证据支持要点**")
                            for point in answer_result["key_points"]:
                                st.markdown(
                                    f"- {point['text']} "
                                    f"**[PDF 第 "
                                    f"{point['page_number']} 页]**"
                                )
                            st.caption(answer_result["limitation"])
                            st.markdown("#### Skeptic Mode / 反方检查")
                            if skeptical_result["challenges"]:
                                st.warning(skeptical_result["summary"])
                                for challenge in skeptical_result["challenges"]:
                                    st.markdown(
                                        f"- {challenge['excerpt']} "
                                        f"**[PDF 第 "
                                        f"{challenge['page_number']} 页]**"
                                    )
                            else:
                                st.info(skeptical_result["summary"])
                            st.caption(skeptical_result["limitation"])
                            show_verification_result(verification_result)
                            if llm_result is not None:
                                show_llm_analyst_result(llm_result)
                            st.markdown("#### 年报原文证据")
                            st.caption(
                                "以下原文按财务术语相关性排序。"
                            )
                            for result_number, result in enumerate(
                                evidence_results,
                                start=1,
                            ):
                                matched_terms = ", ".join(
                                    result["matched_terms"]
                                )
                                matched_concepts = ", ".join(
                                    result.get("matched_concepts", [])
                                )
                                with st.expander(
                                    f"{result_number}. PDF 第 "
                                    f"{result['page_number']} 页",
                                    expanded=result_number == 1,
                                ):
                                    st.text(result["text"])
                                    if matched_concepts:
                                        st.caption(
                                            "识别的财务概念："
                                            f"{matched_concepts}."
                                        )
                                    semantic_score = result.get(
                                        "semantic_score"
                                    )
                                    semantic_text = (
                                        f"{semantic_score:.3f}"
                                        if semantic_score is not None
                                        else "unavailable"
                                    )
                                    st.caption(
                                        "检索方法："
                                        f"{result.get('retrieval_method', 'lexical')}; "
                                        f"本地语义相似度："
                                        f"{semantic_text}."
                                    )
                                    st.caption(
                                        f"匹配词：{matched_terms}。证据来源："
                                        f"{uploaded_report.name}，PDF 第 "
                                        f"{result['page_number']} 页。"
                                    )

            st.subheader("问答质量基准 / Quality Benchmark")
            st.caption(
                "Tesco 2026 回归基准由人工定义正确的路由、计算、"
                "来源页码、升级、质疑和安全拒答；它不是模型自报的"
                "置信度。"
            )
            if uploaded_report.name == "tesco_annual_report_2026.pdf":
                if st.button(
                    "运行 10 个案例的质量基准",
                    use_container_width=True,
                ):
                    with st.spinner("正在评估完整 Agent 工作流……"):
                        benchmark_results, benchmark_summary = (
                            run_uploaded_qa_benchmark(extracted_pages)
                        )
                    st.session_state["tesco_qa_benchmark"] = {
                        "report_name": uploaded_report.name,
                        "results": benchmark_results,
                        "summary": benchmark_summary,
                    }

                stored_benchmark = st.session_state.get(
                    "tesco_qa_benchmark"
                )
                if (
                    stored_benchmark is not None
                    and stored_benchmark["report_name"]
                    == uploaded_report.name
                ):
                    show_qa_benchmark_results(
                        results=stored_benchmark["results"],
                        summary=stored_benchmark["summary"],
                    )
            else:
                st.info(
                    "当前质量基准专门针对 Tesco 2026 年报，"
                    "因此不会应用于本文件。"
                )

            if extracted_figures is not None:
                current_revenue = extracted_figures["current_revenue"]
                previous_revenue = extracted_figures["previous_revenue"]
                current_net_profit = extracted_figures["current_net_profit"]
                previous_net_profit = extracted_figures["previous_net_profit"]
                unit = extracted_figures["unit"] or "报告单位"

                st.subheader("自动提取：收入与利润")
                st.caption(
                    "Python 扫描年报，精确匹配利润表行标签，"
                    "并选取各期间的 Total（合计）列。"
                )
                revenue_column, profit_column = st.columns(2)
                revenue_column.metric(
                    f"营业收入 ({unit})",
                    f"{current_revenue:,.0f}",
                    delta=(
                        f"{current_revenue - previous_revenue:+,.0f} "
                        "较上期"
                    ),
                )
                profit_column.metric(
                    f"年度净利润 ({unit})",
                    f"{current_net_profit:,.0f}",
                    delta=(
                        f"{current_net_profit - previous_net_profit:+,.0f} "
                        "较上期"
                    ),
                )
                st.caption(
                    f"上期合计：营业收入 {previous_revenue:,.0f} {unit}；"
                    f"年度净利润 {previous_net_profit:,.0f} {unit}。"
                )

                if current_revenue != 0 and previous_revenue != 0:
                    automatic_growth = revenue_growth(
                        previous_revenue=previous_revenue,
                        current_revenue=current_revenue,
                    )
                    automatic_margin = net_profit_margin(
                        revenue=current_revenue,
                        net_profit=current_net_profit,
                    )
                    previous_margin = net_profit_margin(
                        revenue=previous_revenue,
                        net_profit=previous_net_profit,
                    )
                    margin_change_points = (
                        automatic_margin - previous_margin
                    ) * 100

                    growth_column, margin_column = st.columns(2)
                    growth_column.metric(
                        "报告口径收入增长率",
                        f"{automatic_growth:.1%}",
                    )
                    margin_column.metric(
                        "净利润率",
                        f"{automatic_margin:.1%}",
                        delta=(
                            f"{margin_change_points:+.1f} 个百分点，较上期"
                        ),
                    )
                    st.caption(
                        f"上期净利润率：{previous_margin:.1%}。"
                    )
                else:
                    st.warning(
                        "当本期或上期收入为零时，系统不会计算增长率和"
                        "利润率比较。"
                    )

                current_weeks = extracted_figures["current_period_weeks"]
                previous_weeks = extracted_figures["previous_period_weeks"]
                if (
                    current_weeks is not None
                    and previous_weeks is not None
                    and current_weeks != previous_weeks
                ):
                    st.warning(
                        f"可比性提示：本期包含 {current_weeks} 周，"
                        f"上期包含 {previous_weeks} 周，因此报告增长率"
                        "并非严格的同口径比较。"
                    )

                st.caption(
                    "证据行：Revenue 与 Profit/(loss) for the year，"
                    f"PDF 第 {extracted_figures['page_number']} 页。"
                )
                st.info(
                    "如果报表结构或行标签不符合预期，提取器会停止，"
                    "不会猜测财务数字。"
                )

            if balance_sheet_figures is not None:
                current_resources = balance_sheet_figures["current_resources"]
                previous_resources = balance_sheet_figures["previous_resources"]
                extracted_current_liabilities = balance_sheet_figures[
                    "current_liabilities"
                ]
                previous_current_liabilities = balance_sheet_figures[
                    "previous_liabilities"
                ]
                current_liquidity_ratio = current_ratio(
                    current_assets=current_resources,
                    current_liabilities=extracted_current_liabilities,
                )
                previous_liquidity_ratio = current_ratio(
                    current_assets=previous_resources,
                    current_liabilities=previous_current_liabilities,
                )
                liquidity_ratio_change = (
                    current_liquidity_ratio - previous_liquidity_ratio
                )
                net_current_position = balance_sheet_figures[
                    "current_net_current_liabilities"
                ]
                assets_held_for_sale = balance_sheet_figures[
                    "current_assets_held_for_sale"
                ]
                liquidity_unit = (
                    balance_sheet_figures["unit"] or "报告单位"
                )

                st.subheader("自动提取：流动性")
                st.caption(
                    "Python 将流动资源减去流动负债，并与报表中的"
                    "净流动负债行进行勾稽核对。"
                )
                resources_column, liabilities_column = st.columns(2)
                resources_column.metric(
                    f"流动资源 ({liquidity_unit})",
                    f"{current_resources:,.0f}",
                )
                liabilities_column.metric(
                    f"流动负债 ({liquidity_unit})",
                    f"{extracted_current_liabilities:,.0f}",
                )
                ratio_column, net_current_column = st.columns(2)
                ratio_column.metric(
                    "流动比率",
                    f"{current_liquidity_ratio:.2f}x",
                    delta=(
                        f"{liquidity_ratio_change:+.2f}x，较上期"
                    ),
                )
                net_current_column.metric(
                    f"净流动负债 ({liquidity_unit})",
                    f"{net_current_position:,.0f}",
                )
                st.caption(
                    f"流动资源 = 流动资产小计 "
                    f"{balance_sheet_figures['current_assets_subtotal']:,.0f} "
                    f"+ 待售资产 "
                    f"{assets_held_for_sale:,.0f} {liquidity_unit}. "
                    f"上期流动比率：{previous_liquidity_ratio:.2f}x。"
                )
                if current_liquidity_ratio < 1:
                    st.warning(
                        "报告日流动资源低于流动负债，表明营运资金为负；"
                        "但这本身不能证明企业资不抵债，还需结合现金流"
                        "和商业模式判断。"
                    )
                st.caption(
                    "证据行：Current assets、Non-current assets classified "
                    "as held for sale、Current liabilities 与 Net current "
                    f"liabilities，PDF 第 "
                    f"{balance_sheet_figures['page_number']} 页。"
                )

                extracted_total_assets = balance_sheet_figures[
                    "current_total_assets"
                ]
                previous_total_assets = balance_sheet_figures[
                    "previous_total_assets"
                ]
                extracted_total_liabilities = balance_sheet_figures[
                    "current_total_liabilities"
                ]
                previous_total_liabilities = balance_sheet_figures[
                    "previous_total_liabilities"
                ]
                automatic_leverage = liabilities_to_assets_ratio(
                    total_assets=extracted_total_assets,
                    total_liabilities=extracted_total_liabilities,
                )
                previous_leverage = liabilities_to_assets_ratio(
                    total_assets=previous_total_assets,
                    total_liabilities=previous_total_liabilities,
                )
                leverage_change_points = (
                    automatic_leverage - previous_leverage
                ) * 100

                st.subheader("自动提取：杠杆与资本结构")
                st.caption(
                    "Python 汇总流动与非流动项目，并验证总资产减总负债"
                    "等于报表净资产。"
                )
                total_assets_column, total_liabilities_column = st.columns(2)
                total_assets_column.metric(
                    f"总资产 ({liquidity_unit})",
                    f"{extracted_total_assets:,.0f}",
                )
                total_liabilities_column.metric(
                    f"总负债 ({liquidity_unit})",
                    f"{extracted_total_liabilities:,.0f}",
                )
                leverage_column, net_assets_column = st.columns(2)
                leverage_column.metric(
                    "资产负债率",
                    f"{automatic_leverage:.1%}",
                    delta=(
                        f"{leverage_change_points:+.1f} 个百分点，较上期"
                    ),
                )
                net_assets_column.metric(
                    f"净资产 ({liquidity_unit})",
                    f"{balance_sheet_figures['current_net_assets']:,.0f}",
                )
                st.caption(
                    f"资产负债表勾稽：{extracted_total_assets:,.0f} − "
                    f"{extracted_total_liabilities:,.0f} = "
                    f"{balance_sheet_figures['current_net_assets']:,.0f} "
                    f"{liquidity_unit}。上期资产负债率："
                    f"{previous_leverage:.1%}。"
                )
                st.info(
                    "该比率反映资产负债表结构，应结合债务条款、"
                    "租赁负债、现金流和企业商业模式共同分析。"
                )
                st.caption(
                    "证据部分：非流动资产、流动资源、流动负债、"
                    "非流动负债和净资产，PDF 第 "
                    f"{balance_sheet_figures['page_number']} 页。"
                )

            if cash_flow_figures is not None:
                cash_flow_unit = cash_flow_figures["unit"] or "报告单位"
                operating_cash = cash_flow_figures[
                    "current_operating_cash_flow"
                ]
                investing_cash = cash_flow_figures[
                    "current_investing_cash_flow"
                ]
                financing_cash = cash_flow_figures[
                    "current_financing_cash_flow"
                ]
                net_cash_change = cash_flow_figures["current_net_cash_change"]
                opening_cash = cash_flow_figures["current_opening_cash"]
                exchange_effect = cash_flow_figures["current_exchange_effect"]
                ending_cash = cash_flow_figures["current_ending_cash"]

                st.subheader("自动提取：现金流")
                st.caption(
                    "Python 同时核对经营、投资、融资三类现金流，"
                    "以及期初至期末现金余额的变动。"
                )
                operating_column, investing_column = st.columns(2)
                operating_column.metric(
                    f"经营活动现金流 ({cash_flow_unit})",
                    f"{operating_cash:,.0f}",
                    delta=(
                        f"{operating_cash - cash_flow_figures[
                            'previous_operating_cash_flow'
                        ]:+,.0f}，较上期"
                    ),
                )
                investing_column.metric(
                    f"投资活动现金流 ({cash_flow_unit})",
                    f"{investing_cash:,.0f}",
                )
                financing_column, ending_cash_column = st.columns(2)
                financing_column.metric(
                    f"融资活动现金流 ({cash_flow_unit})",
                    f"{financing_cash:,.0f}",
                )
                ending_cash_column.metric(
                    f"期末现金 ({cash_flow_unit})",
                    f"{ending_cash:,.0f}",
                )
                st.caption(
                    f"现金流勾稽：{operating_cash:,.0f} + "
                    f"({investing_cash:,.0f}) + ({financing_cash:,.0f}) = "
                    f"{net_cash_change:,.0f} {cash_flow_unit} 净现金变动。"
                )
                st.caption(
                    f"现金余额勾稽：{opening_cash:,.0f} + "
                    f"{net_cash_change:,.0f} + ({exchange_effect:,.0f}) = "
                    f"{ending_cash:,.0f} {cash_flow_unit}。"
                )
                current_cash_weeks = cash_flow_figures["current_period_weeks"]
                previous_cash_weeks = cash_flow_figures[
                    "previous_period_weeks"
                ]
                if (
                    current_cash_weeks is not None
                    and previous_cash_weeks is not None
                    and current_cash_weeks != previous_cash_weeks
                ):
                    st.warning(
                        f"现金流可比性提示：本期包含 {current_cash_weeks} "
                        f"周，上期包含 {previous_cash_weeks} 周。"
                    )
                st.info(
                    "经营现金流为正是重要信号，但其质量仍需结合营运资金、"
                    "经常性经营、资本开支和融资需求判断。"
                )
                st.caption(
                    "证据行：经营、投资和融资净现金流；净现金变动；"
                    "期初与期末现金，PDF 第 "
                    f"{cash_flow_figures['page_number']} 页。"
                )
    else:
        st.info(
            "准备好后请上传公开年度报告 PDF。上传内容只用于本次分析，"
            "不会写入公开代码仓库；请勿上传个人或机密资料。"
        )

    st.divider()
    st.markdown(
        (
            '<div class="wfz-section-label">'
            '02 / 手工财务分析 · FINANCIAL WORKBENCH'
            '</div>'
        ),
        unsafe_allow_html=True,
    )
    st.header("手工财务分析工具")

    st.subheader("净利润率")
    st.write(
        "输入同一报告期的营业收入和净利润。计算由 Python 完成，"
        "不是由 AI 猜测生成。"
    )

    currency = st.selectbox(
        "显示货币",
        options=[
            "CNY (¥ 人民币)",
            "GBP (£ 英镑)",
            "USD ($ 美元)",
            "EUR (€ 欧元)",
            "其他 / Other",
        ],
    )

    with st.form("net_profit_margin_form"):
        revenue = st.number_input(
            "营业收入",
            min_value=0.0,
            value=1_200_000.0,
            step=10_000.0,
            help="企业在该报告期披露的营业收入总额。",
        )
        net_profit = st.number_input(
            "净利润",
            value=120_000.0,
            step=10_000.0,
            help="如果企业报告净亏损，请输入负数。",
        )
        calculate = st.form_submit_button(
            "计算净利润率",
            type="primary",
            use_container_width=True,
        )

    result_area = st.empty()
    if calculate:
        with result_area.container():
            if revenue == 0:
                st.metric("净利润率", "无法计算")
                st.error(
                    "营业收入必须大于零，因为分母为零时无法计算利润率。"
                )
                st.caption(
                    "公式未执行：净利润不能除以零收入。"
                )
            else:
                margin = net_profit_margin(
                    revenue=revenue,
                    net_profit=net_profit,
                )
                st.metric("净利润率", f"{margin:.1%}")
                st.info(explain_net_profit_margin(margin))
                st.caption(
                    f"公式：净利润 ÷ 营业收入 = "
                    f"{net_profit:,.0f} ÷ {revenue:,.0f}"
                )

    with st.expander("如何理解净利润率"):
        st.write(
            "净利润率表示企业每获得一单位收入，最终形成多少净利润或"
            "净亏损。应与企业历史期间及可比公司比较，不同行业的"
            "合理利润率存在差异。"
        )
        st.caption(f"当前显示货币：{currency}")
        st.warning(
            "本工具用于财务分析，不构成投资建议。"
        )

    st.divider()
    st.subheader("营业收入增长率")
    st.write(
        "输入连续两个报告期的营业收入，结果显示本期相对上期的"
        "增长或下降幅度。"
    )

    with st.form("revenue_growth_form"):
        previous_revenue = st.number_input(
            "上期营业收入",
            min_value=0.0,
            value=1_000_000.0,
            step=10_000.0,
        )
        current_revenue = st.number_input(
            "本期营业收入",
            min_value=0.0,
            value=1_200_000.0,
            step=10_000.0,
        )
        calculate_growth = st.form_submit_button(
            "计算收入增长率",
            type="primary",
            use_container_width=True,
        )

    growth_result_area = st.empty()
    if calculate_growth:
        with growth_result_area.container():
            if previous_revenue == 0:
                st.metric("营业收入增长率", "无法计算")
                st.error(
                    "上期营业收入必须大于零，因为它是增长率公式的分母。"
                )
                st.caption(
                    "公式未执行：收入变动额不能除以零。"
                )
            else:
                growth = revenue_growth(
                    previous_revenue=previous_revenue,
                    current_revenue=current_revenue,
                )
                st.metric("营业收入增长率", f"{growth:.1%}")
                st.info(explain_revenue_growth(growth))
                st.caption(
                    "公式：（本期收入 − 上期收入）÷ 上期收入 = "
                    f"({current_revenue:,.0f} − "
                    f"{previous_revenue:,.0f}) ÷ {previous_revenue:,.0f}"
                )

    with st.expander("如何理解营业收入增长率"):
        st.write(
            "正增长表示收入增加，负增长表示收入下降。应同时分析利润、"
            "现金流、并购处置和汇率影响，避免只看单一增长数字。"
        )
        st.caption(f"当前显示货币：{currency}")

    st.divider()
    st.subheader("流动比率")
    st.write(
        "输入同一报告日的流动资产和流动负债，比较企业短期资源"
        "与短期偿债义务。"
    )

    with st.form("current_ratio_form"):
        current_assets = st.number_input(
            "流动资产",
            min_value=0.0,
            value=1_500_000.0,
            step=10_000.0,
        )
        current_liabilities = st.number_input(
            "流动负债",
            min_value=0.0,
            value=1_000_000.0,
            step=10_000.0,
        )
        calculate_current_ratio = st.form_submit_button(
            "计算流动比率",
            type="primary",
            use_container_width=True,
        )

    current_ratio_result_area = st.empty()
    if calculate_current_ratio:
        with current_ratio_result_area.container():
            if current_liabilities == 0:
                st.metric("流动比率", "无法计算")
                st.error(
                    "流动负债必须大于零，因为它是流动比率公式的分母。"
                )
                st.caption(
                    "公式未执行：流动资产不能除以零流动负债。"
                )
            else:
                ratio = current_ratio(
                    current_assets=current_assets,
                    current_liabilities=current_liabilities,
                )
                st.metric("流动比率", f"{ratio:.2f}x")
                st.info(explain_current_ratio(ratio))
                st.caption(
                    "公式：流动资产 ÷ 流动负债 = "
                    f"{current_assets:,.0f} ÷ {current_liabilities:,.0f}"
                )

    with st.expander("如何理解流动比率"):
        st.write(
            "较高的流动比率表示流动资产相对更多，但合理水平取决于"
            "行业和商业模式。还应分析现金流、应收账款和存货质量。"
        )
        st.caption(f"当前显示货币：{currency}")

    st.divider()
    st.subheader("资产负债率")
    st.write(
        "输入同一报告日的总资产和总负债，计算负债占资产总额的比例。"
    )

    with st.form("liabilities_to_assets_form"):
        total_assets = st.number_input(
            "总资产",
            min_value=0.0,
            value=5_000_000.0,
            step=10_000.0,
        )
        total_liabilities = st.number_input(
            "总负债",
            min_value=0.0,
            value=2_000_000.0,
            step=10_000.0,
        )
        calculate_leverage = st.form_submit_button(
            "计算资产负债率",
            type="primary",
            use_container_width=True,
        )

    leverage_result_area = st.empty()
    if calculate_leverage:
        with leverage_result_area.container():
            if total_assets == 0:
                st.metric("资产负债率", "无法计算")
                st.error(
                    "总资产必须大于零，因为它是资产负债率公式的分母。"
                )
                st.caption(
                    "公式未执行：总负债不能除以零总资产。"
                )
            else:
                leverage = liabilities_to_assets_ratio(
                    total_assets=total_assets,
                    total_liabilities=total_liabilities,
                )
                st.metric("资产负债率", f"{leverage:.1%}")
                st.info(explain_liabilities_to_assets_ratio(leverage))
                st.caption(
                    "公式：总负债 ÷ 总资产 = "
                    f"{total_liabilities:,.0f} ÷ {total_assets:,.0f}"
                )

    with st.expander("如何理解资产负债率"):
        st.write(
            "比例越高，说明负债占资产基础的比重越大。应结合历史趋势、"
            "可比公司、债务条款和现金流共同分析。"
        )
        st.caption(f"当前显示货币：{currency}")

    show_product_footer()


def main() -> None:
    """Configure and run the product's multi-page navigation."""
    st.set_page_config(
        page_title="王方正｜中国上市公司研究Agent",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    home_page = st.Page(
        render_home_page,
        title="首页",
        icon="🏠",
        default=True,
    )
    company_page = st.Page(
        render_company_research_page,
        title="公司研究中心",
        icon="🏢",
    )
    market_page = st.Page(
        render_market_page,
        title="K线与市场表现",
        icon="📈",
    )
    historical_page = st.Page(
        render_historical_lens_page,
        title="Historical Lens",
        icon="🕰️",
    )
    annual_page = st.Page(
        render_annual_report_page,
        title="年报与证据",
        icon="📄",
    )
    methodology_page = st.Page(
        render_methodology_page,
        title="方法与审计",
        icon="🧭",
    )
    st.session_state["_wfz_page_registry"] = {
        "home": home_page,
        "company": company_page,
        "market": market_page,
        "historical": historical_page,
        "annual": annual_page,
        "methodology": methodology_page,
    }

    navigation = st.navigation(
        {
            "开始": [home_page],
            "上市公司研究": [
                company_page,
                market_page,
                historical_page,
                annual_page,
            ],
            "产品说明": [methodology_page],
        }
    )
    navigation.run()


if __name__ == "__main__":
    main()
