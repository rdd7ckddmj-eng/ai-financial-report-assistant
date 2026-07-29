import json
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from adaptive_escalation import (
    EscalationDecision,
    decide_adaptive_escalation,
)
from agent_coordinator import (
    AgentTraceStep,
    AgentWorkflowRun,
    build_agent_audit_record,
    run_agent_workflow,
)
from agent_router import RouteDecision, route_question
from answer_verifier import VerificationResult
from balance_sheet_extractor import find_balance_sheet_figures
from cash_flow_extractor import find_cash_flow_figures
from financial_statement_extractor import find_income_statement_figures
from financial_ratios import (
    current_ratio,
    liabilities_to_assets_ratio,
    net_profit_margin,
    revenue_growth,
)
from llm_analyst import (
    LLMAnalystRun,
    run_llm_analyst,
    serialise_llm_run,
)
from pdf_extractor import ExtractedPage, extract_pdf_pages
from qa_benchmark import (
    BenchmarkCaseResult,
    BenchmarkSummary,
    evaluate_benchmark,
    load_benchmark_cases,
    summarise_benchmark,
)
from report_retriever import (
    ReportChunk,
    chunk_report_pages,
)
from report_metric_tool import MetricToolResult


CHINESE_USER_GUIDE_PATH = (
    Path(__file__).resolve().parents[1] / "docs" / "中文使用说明.md"
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
        .stDownloadButton > button {
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

        .stButton > button:hover,
        .stDownloadButton > button:hover {
            border: 0;
            color: white;
            transform: translateY(-1px);
            box-shadow: 0 12px 26px rgba(11, 101, 111, 0.25);
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
                WFZ 金融智能 · 国内求职演示版
            </div>
            <h1 class="wfz-title">
                AI 财务报告<br><span>智能分析助手</span>
            </h1>
            <p class="wfz-subtitle">
                以证据为核心的财务智能产品：Python 负责透明计算，
                PDF 页码保证结论可追溯，多 Agent 工作流负责检索、
                质疑与验证。
            </p>
            <div class="wfz-badges">
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
            file_name="WFZ_AI财报智能分析助手_中文使用说明.md",
            mime="text/markdown",
            use_container_width=True,
        )


def main() -> None:
    st.set_page_config(
        page_title="王方正｜AI财报智能分析助手",
        page_icon="📊",
        layout="wide",
    )

    apply_product_theme()
    show_product_identity()
    show_chinese_user_guide()

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
            "准备好后请上传 PDF。文件只在本地应用中处理，"
            "不会自动离开你的电脑。"
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

    st.markdown(
        """
        <div class="wfz-footer">
            <strong>WFZ 金融智能</strong> · 产品设计与研发：
            <strong>王方正 · Durham University</strong><br>
            以证据为核心的财务分析，用于教育、求职演示与作品集展示。
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
