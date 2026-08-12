import gc
import json
import sys
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from html import escape
from io import BytesIO
from pathlib import Path
from time import perf_counter, time_ns

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
from src.anomaly_report_card import build_anomaly_report_card_html
from src.anomaly_analogs import find_historical_anomaly_analogs
from src.agent_coordinator import (
    AgentTraceStep,
    AgentWorkflowRun,
    build_agent_audit_record,
    run_agent_workflow,
)
from src.agent_router import RouteDecision, route_question
from src.answer_verifier import VerificationResult
from src.audited_company_onboarding import (
    AnnualReportCandidate,
    CandidateReportResult,
    build_candidate_report_result,
    build_onboarding_package,
    pending_annual_reports,
    select_recent_annual_reports,
    serialise_financial_history_draft,
    serialise_onboarding_package,
)
from src.balance_sheet_extractor import find_balance_sheet_figures
from src.browser_research_state import (
    MAX_EVIDENCE_CHECKPOINTS,
    MAX_LOCAL_WATCHLIST,
    MAX_RECENT_RESEARCH,
    MAX_RESEARCH_THESES,
    THESIS_STATUSES,
    THESIS_TOPICS,
    normalise_browser_research_state,
)
from src.baijiu_operating_quality import (
    build_baijiu_operating_quality,
    load_baijiu_operating_quality,
)
from src.cash_flow_extractor import find_cash_flow_figures
from src.cash_case_game import (
    build_cash_defense_question,
    build_cash_evidence_case,
    build_cash_timing_question,
    evaluate_cash_evidence_selection,
)
from src.china_stock import (
    CompanyIdentity,
    DataSourceError,
    MarketActivityEvidence,
    MarketActivityEvent,
    MarketMetrics,
    add_moving_averages,
    build_company_identity,
    calculate_market_activity,
    calculate_market_metrics,
    download_official_pdf,
    fetch_announcements,
    fetch_company_directory,
    fetch_market_history,
    resolve_company,
    scan_market_activity_events,
    select_latest_annual_report,
)
from src.company_industry import audit_company_industry_catalog
from src.comprehensive_research import (
    ComprehensiveResearchBrief,
    build_comprehensive_research_brief,
)
from src.comprehensive_research_report import (
    build_comprehensive_research_audit_payload,
    build_comprehensive_research_report_html,
)
from src.cross_company_comparison import build_cross_company_comparison
from src.evidence_delta import (
    EvidenceDeltaReview,
    build_evidence_delta_report_html,
    build_evidence_delta_review,
    build_evidence_window,
)
from src.financial_statement_extractor import find_income_statement_figures
from src.financial_ratios import (
    current_ratio,
    liabilities_to_assets_ratio,
    net_profit_margin,
    revenue_growth,
)
from src.financial_history import (
    FinancialHistoryCase,
    audit_financial_history_catalog,
    load_financial_history_catalog,
    load_verified_financial_history,
    select_financial_history_as_of,
    verified_financial_history_codes,
)
from src.financial_anomaly_explanation import (
    build_financial_anomaly_review,
    load_financial_anomaly_cases,
)
from src.financial_anomaly_report import (
    build_financial_anomaly_report_html,
)
from src.financial_trend_lab import build_financial_trend_review
from src.flagship_cases import load_moutai_flagship_events
from src.historical_lens import (
    EvidenceRecord,
    EventEvidenceChain,
    build_event_evidence_chain,
    calculate_historical_snapshot,
    calculate_later_outcomes,
    filter_evidence_as_of,
    slice_market_as_of,
)
from src.historical_deep_link import parse_historical_deep_link
from src.historical_game_mission import (
    HISTORICAL_GAME_MISSION,
    HISTORICAL_MISSION_ID,
    build_historical_mission_reasoning_question,
    evaluate_historical_mission_date,
    evaluate_historical_mission_reasoning,
    resolve_historical_mission_clock_boundary,
)
from src.llm_analyst import (
    LLMAnalystRun,
    run_llm_analyst,
    serialise_llm_run,
)
from src.limit_up_board import (
    LimitUpBoardSnapshot,
    build_limit_up_board_snapshot,
    fetch_limit_up_pool,
)
from src.market_anomaly_agent import (
    MarketAnomalyReport,
    build_market_anomaly_report,
)
from src.market_radar import (
    ResearchQueueRow,
    build_market_radar_row,
    build_research_queue_row,
    parse_watchlist_codes,
    rank_research_queue,
)
from src.on_demand_financial_snapshot import (
    OnDemandFinancialSnapshot,
    build_financial_snapshot_report_html,
    build_on_demand_financial_snapshot,
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
from src.research_queue_report import build_research_queue_report_html
from src.research_thesis_ledger import (
    build_thesis_ledger_report_html,
    matching_evidence_items,
    thesis_status_counts,
)
from src.volume_turnover_research import (
    VolumeTurnoverSnapshot,
    build_volume_turnover_history,
    build_volume_turnover_snapshot,
    calculate_effective_turnover,
)


CHINESE_USER_GUIDE_PATH = (
    PROJECT_ROOT / "docs" / "中文使用说明.md"
)
DEFAULT_RESEARCH_LOOKBACK_DAYS = 420
RADAR_RESEARCH_CONTEXT_KEY = "radar_research_context"
COMPREHENSIVE_BRIEF_KEY = "comprehensive_research_brief"
COMPREHENSIVE_ELAPSED_KEY = "comprehensive_research_elapsed_seconds"


_BROWSER_RESEARCH_STORAGE = st.components.v2.component(
    name="wfz_browser_research_storage",
    html='<span class="wfz-browser-storage" aria-hidden="true"></span>',
    css=".wfz-browser-storage { display: none; }",
    js="""
    export default function({ data, setStateValue }) {
      const storageKey = data.storage_key;
      const maxRecent = Number(data.max_recent) || 6;
      const maxWatchlist = Number(data.max_watchlist) || 5;
      const maxEvidenceCheckpoints = Number(data.max_evidence_checkpoints) || 5;
      const maxResearchTheses = Number(data.max_research_theses) || 10;
      const thesisTopics = [
        "财务与业绩", "经营事项", "资本运作", "治理与风险", "其他"
      ];
      const thesisStatuses = [
        "待核验", "暂有证据支持", "出现反方证据", "已失效"
      ];

      const cleanText = (raw, limit, required = false) => {
        if (typeof raw !== "string") return required ? null : "";
        const cleaned = raw.trim().replace(/\\s+/g, " ").slice(0, limit);
        return required && !cleaned ? null : cleaned;
      };

      const isOfficialUrl = (raw) => {
        if (typeof raw !== "string") return false;
        try {
          const parsed = new URL(raw);
          const host = parsed.hostname.toLowerCase();
          const allowed = [
            "cninfo.com.cn", "sse.com.cn", "szse.cn", "bse.cn"
          ];
          return ["http:", "https:"].includes(parsed.protocol) && allowed.some(
            (item) => host === item || host.endsWith(`.${item}`)
          );
        } catch (_) {
          return false;
        }
      };

      const cleanCompany = (raw) => {
        if (!raw || typeof raw !== "object") return null;
        const fields = [
          "code", "name", "exchange", "exchange_name", "canonical_code"
        ];
        const company = {};
        for (const field of fields) {
          const value = typeof raw[field] === "string"
            ? raw[field].trim().slice(0, 80)
            : "";
          if (!value) return null;
          company[field] = value;
        }
        if (!/^\\d{6}$/.test(company.code)) return null;
        if (company.canonical_code !== `${company.code}.${company.exchange}`) {
          return null;
        }
        for (const field of ["last_researched_at", "added_at"]) {
          if (typeof raw[field] === "string" && raw[field].trim()) {
            company[field] = raw[field].trim().slice(0, 40);
          }
        }
        return company;
      };

      const cleanList = (raw, limit) => {
        if (!Array.isArray(raw)) return [];
        const seen = new Set();
        const result = [];
        for (const item of raw) {
          const company = cleanCompany(item);
          if (!company || seen.has(company.canonical_code)) continue;
          seen.add(company.canonical_code);
          result.push(company);
          if (result.length >= limit) break;
        }
        return result;
      };

      const cleanCheckpointList = (raw) => {
        if (!Array.isArray(raw)) return [];
        const seen = new Set();
        const result = [];
        for (const item of raw) {
          const company = cleanCompany(item);
          const checkedAt = typeof item?.evidence_checked_at === "string"
            ? item.evidence_checked_at.trim().slice(0, 40)
            : "";
          if (
            !company ||
            !checkedAt ||
            Number.isNaN(Date.parse(checkedAt)) ||
            seen.has(company.canonical_code)
          ) {
            continue;
          }
          seen.add(company.canonical_code);
          company.evidence_checked_at = checkedAt;
          result.push(company);
          if (result.length >= maxEvidenceCheckpoints) break;
        }
        return result;
      };

      const cleanThesis = (raw) => {
        const company = cleanCompany(raw);
        if (!company) return null;
        const thesisId = cleanText(raw?.thesis_id, 80, true);
        const hypothesis = cleanText(raw?.hypothesis, 240, true);
        const confirmation = cleanText(
          raw?.confirmation_criteria, 360, true
        );
        const invalidation = cleanText(
          raw?.invalidation_criteria, 360, true
        );
        const createdAt = cleanText(raw?.created_at, 40, true);
        const updatedAt = cleanText(raw?.updated_at, 40, true);
        if (
          !thesisId || !hypothesis || !confirmation || !invalidation ||
          !thesisTopics.includes(raw?.topic) ||
          !thesisStatuses.includes(raw?.status) ||
          !createdAt || Number.isNaN(Date.parse(createdAt)) ||
          !updatedAt || Number.isNaN(Date.parse(updatedAt))
        ) {
          return null;
        }
        Object.assign(company, {
          thesis_id: thesisId,
          hypothesis,
          confirmation_criteria: confirmation,
          invalidation_criteria: invalidation,
          topic: raw.topic,
          status: raw.status,
          created_at: createdAt,
          updated_at: updatedAt,
        });
        const reviewNote = cleanText(raw?.review_note, 360);
        if (reviewNote) company.review_note = reviewNote;
        const evidenceTitle = cleanText(raw?.evidence_title, 300);
        const evidenceUrl = cleanText(raw?.evidence_url, 500);
        const evidenceDate = cleanText(raw?.evidence_date, 10);
        if (
          evidenceTitle && evidenceUrl && evidenceDate &&
          isOfficialUrl(evidenceUrl) &&
          !Number.isNaN(Date.parse(evidenceDate))
        ) {
          Object.assign(company, {
            evidence_title: evidenceTitle,
            evidence_url: evidenceUrl,
            evidence_date: evidenceDate,
          });
        }
        return company;
      };

      const cleanThesisList = (raw) => {
        if (!Array.isArray(raw)) return [];
        const seen = new Set();
        const result = [];
        for (const item of raw) {
          const thesis = cleanThesis(item);
          if (!thesis || seen.has(thesis.thesis_id)) continue;
          seen.add(thesis.thesis_id);
          result.push(thesis);
          if (result.length >= maxResearchTheses) break;
        }
        return result;
      };

      const cleanSnapshot = (raw, status = "pending") => ({
        version: 3,
        recent: cleanList(raw?.recent, maxRecent),
        watchlist: cleanList(raw?.watchlist, maxWatchlist),
        evidence_checkpoints: cleanCheckpointList(raw?.evidence_checkpoints),
        research_theses: cleanThesisList(raw?.research_theses),
        last_command_id:
          typeof raw?.last_command_id === "string"
            ? raw.last_command_id.slice(0, 80)
            : null,
        storage_status: ["pending", "available", "unavailable"].includes(
          raw?.storage_status
        ) ? raw.storage_status : status,
      });

      let snapshot;
      let storageAvailable = true;
      try {
        const stored = JSON.parse(localStorage.getItem(storageKey) || "null");
        snapshot = cleanSnapshot(stored, "available");
        snapshot.storage_status = "available";
      } catch (_) {
        storageAvailable = false;
        snapshot = cleanSnapshot(data.known_snapshot, "unavailable");
        snapshot.storage_status = "unavailable";
      }

      const command = data.command;
      const company = cleanCompany(command?.company);
      if (
        company &&
        typeof command?.id === "string" &&
        command.id &&
        [
          "record_research",
          "toggle_watchlist",
          "save_evidence_checkpoint",
          "save_research_thesis",
          "update_research_thesis",
          "delete_research_thesis",
        ].includes(command.action) &&
        command.id !== snapshot.last_command_id
      ) {
        const code = company.canonical_code;
        const timestamp = String(command.timestamp || "").slice(0, 40);
        const timestampIsValid = Boolean(timestamp) && !Number.isNaN(
          Date.parse(timestamp)
        );
        let applied = false;
        if (command.action === "record_research") {
          company.last_researched_at = timestamp;
          snapshot.recent = [
            company,
            ...snapshot.recent.filter((item) => item.canonical_code !== code),
          ].slice(0, maxRecent);
          applied = true;
        } else if (command.action === "toggle_watchlist") {
          const exists = snapshot.watchlist.some(
            (item) => item.canonical_code === code
          );
          if (exists) {
            snapshot.watchlist = snapshot.watchlist.filter(
              (item) => item.canonical_code !== code
            );
          } else {
            company.added_at = String(command.timestamp || "").slice(0, 40);
            snapshot.watchlist = [company, ...snapshot.watchlist].slice(
              0,
              maxWatchlist
            );
          }
          applied = true;
        } else if (command.action === "save_evidence_checkpoint") {
          company.evidence_checked_at = timestamp;
          if (timestampIsValid) {
            snapshot.evidence_checkpoints = [
              company,
              ...snapshot.evidence_checkpoints.filter(
                (item) => item.canonical_code !== code
              ),
            ].slice(0, maxEvidenceCheckpoints);
            applied = true;
          }
        } else if (
          command.action === "save_research_thesis" && timestampIsValid
        ) {
          const thesis = cleanThesis({
            ...company,
            thesis_id: command.thesis_id,
            hypothesis: command.hypothesis,
            confirmation_criteria: command.confirmation_criteria,
            invalidation_criteria: command.invalidation_criteria,
            topic: command.topic,
            status: "待核验",
            created_at: timestamp,
            updated_at: timestamp,
          });
          if (thesis) {
            snapshot.research_theses = [
              thesis,
              ...snapshot.research_theses.filter(
                (item) => item.thesis_id !== thesis.thesis_id
              ),
            ].slice(0, maxResearchTheses);
            applied = true;
          }
        } else if (
          command.action === "update_research_thesis" && timestampIsValid
        ) {
          const thesisId = cleanText(command.thesis_id, 80, true);
          const index = snapshot.research_theses.findIndex(
            (item) => item.thesis_id === thesisId &&
              item.canonical_code === code
          );
          if (index >= 0 && thesisStatuses.includes(command.status)) {
            const thesis = cleanThesis({
              ...snapshot.research_theses[index],
              status: command.status,
              updated_at: timestamp,
              review_note: command.review_note,
              evidence_title: command.evidence_title,
              evidence_url: command.evidence_url,
              evidence_date: command.evidence_date,
            });
            if (thesis) {
              snapshot.research_theses[index] = thesis;
              applied = true;
            }
          }
        } else if (command.action === "delete_research_thesis") {
          const thesisId = cleanText(command.thesis_id, 80, true);
          if (thesisId) {
            snapshot.research_theses = snapshot.research_theses.filter(
              (item) => !(
                item.thesis_id === thesisId && item.canonical_code === code
              )
            );
            applied = true;
          }
        }
        if (applied) {
          snapshot.last_command_id = command.id.slice(0, 80);
          if (storageAvailable) {
            try {
              localStorage.setItem(storageKey, JSON.stringify(snapshot));
            } catch (_) {
              snapshot.storage_status = "unavailable";
            }
          }
        }
      }

      const known = cleanSnapshot(data.known_snapshot);
      if (JSON.stringify(snapshot) !== JSON.stringify(known)) {
        setStateValue("snapshot", snapshot);
      }
    }
    """,
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
    source_pages = result.get("source_pages", [])
    page_text = "、".join(str(page) for page in source_pages)
    if not page_text:
        page_text = str(result["source_page"])
    st.caption(
        "本结果由 Python 确定性计算。证据来源：PDF 第 "
        f"{page_text} 页。"
    )


def _statement_page_label(figures: Mapping[str, object]) -> str:
    """Format a single PDF page or an inclusive statement page range."""
    start_page = int(figures["page_number"])
    end_page = int(figures.get("end_page_number", start_page))
    if start_page == end_page:
        return str(start_page)
    return f"{start_page}–{end_page}"


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


@st.cache_data(ttl=1800, max_entries=1, show_spinner=False)
def read_uploaded_pdf(pdf_bytes: bytes) -> list[ExtractedPage]:
    """Temporarily cache only the most recently extracted PDF."""
    return extract_pdf_pages(pdf_bytes)


@st.cache_data(ttl=1800, max_entries=1, show_spinner=False)
def build_search_chunks(
    pages: list[ExtractedPage],
) -> list[ReportChunk]:
    """Temporarily cache chunks for only the most recent report."""
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

        [data-testid="stToolbarActions"],
        #MainMenu,
        footer {
            visibility: hidden;
            height: 0;
        }

        [data-testid="stToolbar"] {
            visibility: visible;
            height: auto;
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

        /* Institutional research-terminal shell. The original theme remains
           underneath as a safe fallback for older Streamlit versions. */
        .stApp {
            background:
                radial-gradient(
                    circle at 10% 0%,
                    rgba(0, 163, 154, 0.08),
                    transparent 28rem
                ),
                radial-gradient(
                    circle at 92% 8%,
                    rgba(212, 174, 98, 0.10),
                    transparent 24rem
                ),
                linear-gradient(180deg, #f8fafc 0%, #f3f6fa 100%);
            font-family:
                Inter, "SF Pro Display", "PingFang SC", "Microsoft YaHei",
                "Helvetica Neue", Arial, sans-serif;
        }

        [data-testid="stHeader"] {
            height: 3.2rem;
            background: rgba(248, 250, 252, 0.84);
            border-bottom: 1px solid rgba(22, 61, 103, 0.06);
            backdrop-filter: blur(16px);
        }

        /* The close and reopen controls must always remain discoverable. */
        [data-testid="stSidebarCollapseButton"] {
            visibility: visible !important;
            opacity: 1 !important;
        }

        [data-testid="stSidebarCollapseButton"] button,
        [data-testid="stSidebarCollapsedControl"] button,
        [data-testid="stExpandSidebarButton"] {
            width: 2.35rem;
            height: 2.35rem;
            border: 1px solid rgba(255, 255, 255, 0.12) !important;
            border-radius: 11px !important;
            background: rgba(255, 255, 255, 0.09) !important;
            box-shadow: 0 8px 22px rgba(2, 12, 25, 0.22) !important;
        }

        [data-testid="stSidebarCollapsedControl"] {
            position: fixed !important;
            top: 0.45rem !important;
            left: 0.65rem !important;
            z-index: 999999 !important;
            display: block !important;
            visibility: visible !important;
            opacity: 1 !important;
        }

        [data-testid="stExpandSidebarButton"] {
            position: fixed !important;
            top: 0.45rem !important;
            left: 0.65rem !important;
            z-index: 999999 !important;
            display: inline-flex !important;
            visibility: visible !important;
            opacity: 1 !important;
            border-color: rgba(7, 24, 46, 0.12) !important;
            background: #07182e !important;
        }

        [data-testid="stSidebarCollapsedControl"] button {
            border-color: rgba(7, 24, 46, 0.12) !important;
            background: #07182e !important;
        }

        [data-testid="stSidebarCollapsedControl"] span,
        [data-testid="stSidebarCollapseButton"] span,
        [data-testid="stExpandSidebarButton"] span {
            color: #ffffff !important;
        }

        section[data-testid="stSidebar"] {
            border-right: 1px solid rgba(255, 255, 255, 0.08);
            background:
                radial-gradient(
                    circle at 30% -5%,
                    rgba(0, 163, 154, 0.24),
                    transparent 18rem
                ),
                linear-gradient(180deg, #07182e 0%, #0a203b 100%);
            box-shadow: 18px 0 50px rgba(7, 24, 46, 0.12);
        }

        [data-testid="stSidebarHeader"] {
            min-height: 5.5rem;
            padding: 1.15rem 1rem 0.8rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        }

        [data-testid="stSidebarHeader"]::before {
            content: "FANGZHENG  AI";
            display: flex;
            align-items: center;
            min-height: 2.3rem;
            padding-left: 0.15rem;
            color: #ffffff;
            font-size: 0.82rem;
            font-weight: 800;
            letter-spacing: 0.16em;
        }

        [data-testid="stSidebarNav"] {
            padding: 1rem 0.7rem 1.5rem;
        }

        [data-testid="stNavSectionHeader"] p {
            margin-top: 0.7rem;
            color: #7790aa !important;
            font-size: 0.66rem;
            font-weight: 800;
            letter-spacing: 0.13em;
        }

        [data-testid="stSidebarNavLink"] {
            min-height: 2.65rem;
            margin: 0.18rem 0;
            border: 1px solid transparent;
            border-radius: 11px;
            transition:
                background 150ms ease,
                border-color 150ms ease,
                transform 150ms ease;
        }

        [data-testid="stSidebarNavLink"] p,
        [data-testid="stSidebarNavLink"] span {
            color: #d9e5f2 !important;
            font-size: 0.86rem;
            font-weight: 620;
        }

        [data-testid="stSidebarNavLink"]:hover {
            border-color: rgba(255, 255, 255, 0.08);
            background: rgba(255, 255, 255, 0.07);
            transform: translateX(2px);
        }

        [data-testid="stSidebarNavLink"][aria-current="page"],
        a[aria-current="page"] [data-testid="stSidebarNavLink"] {
            border-color: rgba(83, 220, 207, 0.22);
            background: linear-gradient(
                100deg,
                rgba(0, 163, 154, 0.28),
                rgba(255, 255, 255, 0.07)
            );
            box-shadow: inset 3px 0 0 #4dd6ca;
        }

        .wfz-hero-grid {
            position: relative;
            z-index: 1;
            display: grid;
            grid-template-columns: minmax(0, 1.45fr) minmax(250px, 0.7fr);
            gap: 2.8rem;
            align-items: center;
        }

        .wfz-terminal {
            position: relative;
            z-index: 1;
            overflow: hidden;
            padding: 1.1rem;
            border: 1px solid rgba(255, 255, 255, 0.14);
            border-radius: 21px;
            background: rgba(3, 15, 30, 0.38);
            box-shadow:
                0 24px 60px rgba(0, 0, 0, 0.22),
                inset 0 1px 0 rgba(255, 255, 255, 0.08);
            backdrop-filter: blur(18px);
        }

        .wfz-terminal-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0.15rem 0.15rem 0.9rem;
            color: rgba(255, 255, 255, 0.48);
            font-size: 0.63rem;
            font-weight: 750;
            letter-spacing: 0.13em;
        }

        .wfz-live {
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            color: #8fe4dc;
        }

        .wfz-live::before {
            content: "";
            width: 0.48rem;
            height: 0.48rem;
            border-radius: 50%;
            background: #57d7ca;
            box-shadow: 0 0 0 0.22rem rgba(87, 215, 202, 0.13);
        }

        .wfz-terminal-row {
            display: grid;
            grid-template-columns: 2.2rem 1fr auto;
            gap: 0.75rem;
            align-items: center;
            margin-top: 0.58rem;
            padding: 0.8rem;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 14px;
            background: rgba(255, 255, 255, 0.05);
        }

        .wfz-terminal-index {
            color: rgba(255, 255, 255, 0.32);
            font-size: 0.68rem;
            font-weight: 800;
        }

        .wfz-terminal-label {
            color: #ffffff;
            font-size: 0.79rem;
            font-weight: 650;
        }

        .wfz-terminal-detail {
            margin-top: 0.2rem;
            color: rgba(255, 255, 255, 0.45);
            font-size: 0.66rem;
        }

        .wfz-terminal-status {
            padding: 0.3rem 0.5rem;
            border-radius: 999px;
            background: rgba(87, 215, 202, 0.12);
            color: #8fe4dc;
            font-size: 0.58rem;
            font-weight: 800;
            letter-spacing: 0.08em;
        }

        .wfz-platform-hero {
            position: relative;
            overflow: hidden;
            margin-bottom: 1.7rem;
            padding: 3.4rem;
            border: 1px solid rgba(22, 61, 103, 0.10);
            border-radius: 30px;
            background:
                radial-gradient(
                    circle at 88% 16%,
                    rgba(86, 185, 217, 0.20),
                    transparent 25rem
                ),
                linear-gradient(135deg, #ffffff 0%, #edf7fb 100%);
            box-shadow: 0 24px 64px rgba(17, 49, 80, 0.10);
        }

        .wfz-platform-hero::after {
            content: "";
            position: absolute;
            width: 330px;
            height: 330px;
            right: -95px;
            bottom: -180px;
            border: 1px solid rgba(22, 61, 103, 0.10);
            border-radius: 50%;
            box-shadow:
                0 0 0 58px rgba(22, 61, 103, 0.025),
                0 0 0 116px rgba(22, 61, 103, 0.018);
        }

        .wfz-platform-kicker {
            position: relative;
            z-index: 1;
            margin-bottom: 1.05rem;
            color: #23749b;
            font-size: 0.75rem;
            font-weight: 850;
            letter-spacing: 0.17em;
        }

        .wfz-platform-title {
            position: relative;
            z-index: 1;
            max-width: 900px;
            margin: 0;
            color: #102d4a;
            font-size: clamp(2.5rem, 5.7vw, 4.8rem);
            font-weight: 760;
            letter-spacing: -0.055em;
            line-height: 1.02;
        }

        .wfz-platform-title span {
            color: #277ca4;
        }

        .wfz-platform-subtitle {
            position: relative;
            z-index: 1;
            max-width: 760px;
            margin: 1.35rem 0 0;
            color: #597188;
            font-size: 1.02rem;
            line-height: 1.75;
        }

        .wfz-module-card {
            min-height: 285px;
            margin-bottom: 0.7rem;
            padding: 1.7rem;
            border: 1px solid rgba(22, 61, 103, 0.12);
            border-radius: 22px;
            background: rgba(255, 255, 255, 0.92);
            box-shadow: 0 18px 42px rgba(17, 49, 80, 0.07);
        }

        .wfz-module-card--game {
            background:
                linear-gradient(145deg, rgba(255,255,255,0.98), rgba(233,247,252,0.92));
        }

        .wfz-module-card--research {
            background:
                linear-gradient(145deg, rgba(255,255,255,0.98), rgba(239,244,251,0.92));
        }

        .wfz-module-number {
            color: #2c7ca2;
            font-size: 0.68rem;
            font-weight: 850;
            letter-spacing: 0.14em;
        }

        .wfz-module-card h2 {
            margin: 1.1rem 0 0.55rem;
            padding: 0;
            font-size: 1.55rem;
        }

        .wfz-module-card p {
            min-height: 4.7rem;
            margin: 0;
            color: #5f7185;
            font-size: 0.88rem;
            line-height: 1.7;
        }

        .wfz-module-path {
            margin-top: 1rem;
            padding-top: 0.9rem;
            border-top: 1px solid rgba(22, 61, 103, 0.10);
            color: #214b6d;
            font-size: 0.74rem;
            font-weight: 720;
            letter-spacing: 0.03em;
        }

        .wfz-learning-loop {
            display: grid;
            grid-template-columns: repeat(6, minmax(0, 1fr));
            gap: 0.65rem;
            margin: 1rem 0 1.4rem;
        }

        .wfz-learning-step {
            padding: 0.9rem 0.55rem;
            border: 1px solid rgba(22, 61, 103, 0.11);
            border-radius: 14px;
            background: rgba(255, 255, 255, 0.90);
            color: #1d4b6e;
            text-align: center;
            font-size: 0.79rem;
            font-weight: 760;
        }

        .wfz-page-intro {
            margin-bottom: 1.7rem;
            padding: 1.55rem 1.7rem;
            border: 1px solid var(--wfz-line);
            border-radius: 20px;
            background:
                linear-gradient(
                    115deg,
                    rgba(255, 255, 255, 0.97),
                    rgba(240, 248, 249, 0.88)
                );
            box-shadow: 0 14px 38px rgba(17, 49, 80, 0.07);
        }

        .wfz-page-intro h1 {
            margin: 0.2rem 0 0.5rem;
            padding: 0;
            font-size: clamp(1.75rem, 3.2vw, 2.45rem);
            line-height: 1.12;
        }

        .wfz-page-intro p {
            max-width: 820px;
            margin: 0;
            color: var(--wfz-muted);
            font-size: 0.94rem;
            line-height: 1.65;
        }

        .wfz-capability-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 1rem;
            margin: 1rem 0 2rem;
        }

        .wfz-capability {
            min-height: 178px;
            padding: 1.35rem;
            border: 1px solid var(--wfz-line);
            border-radius: 18px;
            background: rgba(255, 255, 255, 0.88);
            box-shadow: 0 14px 34px rgba(17, 49, 80, 0.06);
        }

        .wfz-capability-number {
            color: var(--wfz-teal);
            font-size: 0.64rem;
            font-weight: 850;
            letter-spacing: 0.14em;
        }

        .wfz-capability h3 {
            margin: 1rem 0 0.55rem;
            padding: 0;
            font-size: 1.05rem;
        }

        .wfz-capability p {
            margin: 0;
            color: var(--wfz-muted);
            font-size: 0.82rem;
            line-height: 1.65;
        }

        .wfz-scope-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 1rem;
            margin: 1rem 0 1.2rem;
        }

        .wfz-scope-card {
            min-height: 236px;
            padding: 1.45rem;
            border: 1px solid var(--wfz-line);
            border-top: 4px solid var(--wfz-teal);
            border-radius: 19px;
            background: rgba(255, 255, 255, 0.90);
            box-shadow: 0 14px 34px rgba(17, 49, 80, 0.06);
        }

        .wfz-scope-card--verified {
            border-top-color: #c49a4b;
        }

        .wfz-scope-label {
            color: var(--wfz-teal);
            font-size: 0.65rem;
            font-weight: 850;
            letter-spacing: 0.14em;
        }

        .wfz-scope-card--verified .wfz-scope-label {
            color: #9a712a;
        }

        .wfz-scope-card h3 {
            margin: 0.8rem 0 0.55rem;
            padding: 0;
            font-size: 1.15rem;
        }

        .wfz-scope-stat {
            margin-bottom: 0.8rem;
            color: var(--wfz-navy);
            font-size: 0.95rem;
            font-weight: 780;
        }

        .wfz-scope-card p,
        .wfz-scope-names {
            margin: 0;
            color: var(--wfz-muted);
            font-size: 0.81rem;
            line-height: 1.65;
        }

        .wfz-scope-names {
            margin-top: 0.75rem;
            padding-top: 0.75rem;
            border-top: 1px solid var(--wfz-line);
        }

        .wfz-scope-boundary {
            grid-column: 1 / -1;
            display: grid;
            grid-template-columns: minmax(150px, 0.32fr) minmax(0, 1fr);
            gap: 1rem;
            align-items: center;
            padding: 1.05rem 1.3rem;
            border: 1px solid rgba(16, 45, 74, 0.12);
            border-radius: 16px;
            background: rgba(16, 45, 74, 0.045);
        }

        .wfz-scope-boundary strong {
            color: var(--wfz-navy);
            font-size: 0.82rem;
            letter-spacing: 0.04em;
        }

        .wfz-scope-boundary span {
            color: var(--wfz-muted);
            font-size: 0.78rem;
            line-height: 1.6;
        }

        [data-testid="stTextInputRootElement"],
        [data-testid="stTextAreaRootElement"],
        [data-baseweb="select"] > div {
            border-color: var(--wfz-line) !important;
            border-radius: 12px !important;
            background: rgba(255, 255, 255, 0.94) !important;
        }

        [data-testid="stVerticalBlockBorderWrapper"] {
            border-color: var(--wfz-line) !important;
            border-radius: 18px !important;
            background: rgba(255, 255, 255, 0.82);
            box-shadow: 0 12px 32px rgba(17, 49, 80, 0.05);
        }

        @media (max-width: 920px) {
            .wfz-hero-grid {
                grid-template-columns: 1fr;
            }

            .wfz-terminal {
                display: none;
            }

            .wfz-capability-grid {
                grid-template-columns: 1fr;
            }

            .wfz-learning-loop {
                grid-template-columns: repeat(3, minmax(0, 1fr));
            }

            .wfz-scope-grid,
            .wfz-scope-boundary {
                grid-template-columns: 1fr;
            }
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

            .wfz-platform-hero {
                padding: 2rem 1.4rem;
                border-radius: 22px;
            }

            .wfz-platform-title {
                font-size: 2.45rem;
            }

            .wfz-title {
                font-size: 2.55rem;
            }

            .wfz-subtitle {
                font-size: 0.92rem;
            }

            .wfz-page-intro {
                padding: 1.25rem;
            }

            [data-testid="stSidebarCollapsedControl"] {
                top: 0.35rem !important;
                left: 0.45rem !important;
            }

            [data-testid="stExpandSidebarButton"] {
                top: 0.35rem !important;
                left: 0.45rem !important;
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
            <div class="wfz-hero-grid">
                <div>
                    <div class="wfz-kicker">
                        FANGZHENG AI · FROM TICKER TO TRACEABLE RESEARCH
                    </div>
                    <h1 class="wfz-title">
                        从一个股票代码开始<br><span>完成一轮可追溯公司研究</span>
                    </h1>
                    <p class="wfz-subtitle">
                        面向个人投资者、初级分析人员和金融学生的 A 股初步研究
                        工作台。输入公司名称或股票代码，系统把分散在行情、公告
                        和年报中的公开信息接成一条研究链，计算关键指标、指出
                        值得继续核验的问题，并形成附来源的研究底稿。
                    </p>
                    <div class="wfz-badges">
                        <span class="wfz-badge">一个代码统一入口</span>
                        <span class="wfz-badge">官方公开资料</span>
                        <span class="wfz-badge">PYTHON 确定性计算</span>
                        <span class="wfz-badge">来源与页码溯源</span>
                        <span class="wfz-badge">不提供投资建议</span>
                    </div>
                    <div class="wfz-author">
                        <div class="wfz-monogram">WFZ</div>
                        <div>
                            <span class="wfz-author-label">
                                DESIGNED &amp; DEVELOPED BY
                            </span>
                            <span class="wfz-author-name">
                                王方正 · Durham University
                            </span>
                        </div>
                    </div>
                </div>
                <aside class="wfz-terminal">
                    <div class="wfz-terminal-head">
                        <span>RESEARCH PIPELINE</span>
                        <span class="wfz-live">SYSTEM READY</span>
                    </div>
                    <div class="wfz-terminal-row">
                        <span class="wfz-terminal-index">01</span>
                        <div>
                            <div class="wfz-terminal-label">建立标的档案</div>
                            <div class="wfz-terminal-detail">身份 · 行情 · 公告 · 年报</div>
                        </div>
                        <span class="wfz-terminal-status">COLLECT</span>
                    </div>
                    <div class="wfz-terminal-row">
                        <span class="wfz-terminal-index">02</span>
                        <div>
                            <div class="wfz-terminal-label">分析并提出问题</div>
                            <div class="wfz-terminal-detail">指标 · 异动 · 趋势 · 比较</div>
                        </div>
                        <span class="wfz-terminal-status">ANALYSE</span>
                    </div>
                    <div class="wfz-terminal-row">
                        <span class="wfz-terminal-index">03</span>
                        <div>
                            <div class="wfz-terminal-label">形成可复核底稿</div>
                            <div class="wfz-terminal-detail">发现 · 来源 · 页码 · 局限</div>
                        </div>
                        <span class="wfz-terminal-status">DELIVER</span>
                    </div>
                </aside>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def show_platform_identity() -> None:
    """Introduce the two connected halves of the platform."""
    st.markdown(
        """
        <section class="wfz-platform-hero">
            <div class="wfz-platform-kicker">
                FANGZHENG AI · FINANCIAL RESEARCH LAB
            </div>
            <h1 class="wfz-platform-title">
                从学会分析开始<br><span>到独立完成一份研究判断</span>
            </h1>
            <p class="wfz-platform-subtitle">
                一个平台，两种使用方式：在剧情案件中训练金融研究思维，
                或进入真实公司研究终端，核验行情、公告、年报和历史证据。
                两个模块共享同一套证据标准与时间纪律。
            </p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def show_platform_modules() -> None:
    """Render the platform's two primary and connected entry points."""
    game_column, research_column = st.columns(2)
    with game_column:
        st.markdown(
            """
            <article class="wfz-module-card wfz-module-card--game">
                <div class="wfz-module-number">MODULE 01 / LEARN BY DOING</div>
                <h2>研究员任务局</h2>
                <p>
                    通过剧情、调查和答辩，从零学习怎样阅读材料、寻找证据、
                    控制前视偏差，并形成有边界的金融判断。
                </p>
                <div class="wfz-module-path">教 → 练 → 查 → 证 → 辩 → 迁</div>
            </article>
            """,
            unsafe_allow_html=True,
        )
        if st.button(
            "进入研究员任务局",
            type="primary",
            width="stretch",
            key="home_to_game_hub",
        ):
            _switch_page("game")

    with research_column:
        st.markdown(
            """
            <article class="wfz-module-card wfz-module-card--research">
                <div class="wfz-module-number">MODULE 02 / RESEARCH WITH EVIDENCE</div>
                <h2>公司研究终端</h2>
                <p>
                    输入公司名称或股票代码，把公开行情、官方公告、年度报告
                    和历史时点接成一条可以回到来源核验的研究链。
                </p>
                <div class="wfz-module-path">选择公司 → 核验资料 → 形成研究底稿</div>
            </article>
            """,
            unsafe_allow_html=True,
        )
        if st.button(
            "进入公司研究终端",
            width="stretch",
            key="home_to_research_terminal",
        ):
            _switch_page("research_terminal")


def show_home_capabilities() -> None:
    """Explain the three connected jobs completed by the product."""
    st.markdown(
        """
        <div class="wfz-section-label">
            网站能完成什么 · WHAT IT DOES
        </div>
        <div class="wfz-capability-grid">
            <article class="wfz-capability">
                <div class="wfz-capability-number">01 / COLLECT</div>
                <h3>把核心资料接到同一入口</h3>
                <p>
                    核验公司身份，按需连接公开行情、官方公告和年度报告，
                    减少在多个网站之间反复检索和整理。
                </p>
            </article>
            <article class="wfz-capability">
                <div class="wfz-capability-number">02 / ANALYSE</div>
                <h3>把数据变成可继续核验的问题</h3>
                <p>
                    用 Python 计算财务趋势、收益、波动、成交和异动，
                    再由 Agent 连接公告、年报和历史情境进行质疑与解释。
                </p>
            </article>
            <article class="wfz-capability">
                <div class="wfz-capability-number">03 / DELIVER</div>
                <h3>输出一份可复核的研究底稿</h3>
                <p>
                    汇总关键发现、反方问题、来源链接、年报页码和证据缺口，
                    并可在下次回来时核验新增官方证据，支持下载后继续比较、
                    复盘或与他人讨论。
                </p>
            </article>
        </div>
        """,
        unsafe_allow_html=True,
    )


def show_home_value_proposition() -> None:
    """State the research problem, user outcome, and defensible advantages."""
    st.markdown(
        '<div class="wfz-section-label">'
        "产品用途与客户价值 · PURPOSE & VALUE"
        "</div>",
        unsafe_allow_html=True,
    )
    st.subheader("更快完成有证据的第一轮公司研究")
    st.write(
        "上市公司资料分散、年报篇幅长，而普通 AI 回答又可能混淆来源或"
        "生成无法核对的数字。本产品的目的，是把“寻找资料、计算指标、"
        "提出问题、回到原文核验、整理研究结果”连成一条统一流程。"
    )
    st.info(
        "用户最终得到的不是一个简单的‘好或不好’，而是一份知道数字从"
        "哪里来、哪些判断已有证据、哪些问题仍需继续调查的研究底稿。"
    )
    benefit_columns = st.columns(3)
    with benefit_columns[0].container(border=True):
        st.markdown("#### 减少前期资料整理")
        st.write(
            "用一个公司名称或代码进入统一研究流程，减少重复搜索、复制和"
            "手工计算，把时间留给真正的判断。"
        )
    with benefit_columns[1].container(border=True):
        st.markdown("#### 降低错误与遗漏风险")
        st.write(
            "数字由规则计算，结论保留来源和页码；数据不足或来源失败时"
            "明确提示，不把缺失值伪装成确定答案。"
        )
    with benefit_columns[2].container(border=True):
        st.markdown("#### 让研究可以复核和复用")
        st.write(
            "同一套框架可用于不同公司、不同年份和历史时点，方便比较、"
            "复盘、团队讨论和后续深入研究。"
        )

    st.markdown("#### 本产品真正的优势")
    st.write(
        "优势不在于拥有比 Wind 等商业数据库更多的数据，而在于把公开资料"
        "转化为一条透明、低成本、可审计的研究工作流：官方披露优先；"
        "Python 负责数字，AI 只负责基于证据解释和质疑；历史回看隔离未来"
        "信息；本机基准支持持续追踪新增证据；任何一条数据链失败都不会被"
        " AI 猜测补齐。"
    )


def show_home_research_scope() -> None:
    """State broad on-demand access and narrow audited depth separately."""
    try:
        catalog_audit = audit_financial_history_catalog()
    except ValueError:
        verified_stat = "深度案例正在进行独立核验"
        verified_names = "核验完成后才会进入深度研究目录"
    else:
        verified_stat = (
            f"{catalog_audit['company_count']} 家公司 · "
            f"{catalog_audit['financial_period_count']} 个财务期间 · "
            f"{catalog_audit['publication_vintage_count']} 个发布版本"
        )
        verified_names = " · ".join(
            case["company_name"] for case in catalog_audit["cases"]
        )

    st.markdown(
        f"""
        <div class="wfz-section-label">
            产品覆盖 · RESEARCH COVERAGE
        </div>
        <div class="wfz-scope-grid">
            <article class="wfz-scope-card">
                <div class="wfz-scope-label">01 / ON-DEMAND A-SHARE</div>
                <h3>A 股按需研究层</h3>
                <div class="wfz-scope-stat">沪 · 深 · 北交易所代码入口</div>
                <p>
                    输入公司名称或六位代码后，系统按需核验公司身份、公开日线、
                    官方公告和最近年报入口。资料不需要预先批量下载或永久保存；
                    每次结果以公开数据源当时的可用性为准。
                </p>
            </article>
            <article class="wfz-scope-card wfz-scope-card--verified">
                <div class="wfz-scope-label">02 / AUDITED DEEP-DIVE</div>
                <h3>已核验深度案例层</h3>
                <div class="wfz-scope-stat">{escape(verified_stat)}</div>
                <p>
                    只有通过公司身份、年度连续性、官方来源、年报页码和会计口径
                    检查的资料，才进入多年趋势与横向比较。
                </p>
                <div class="wfz-scope-names">
                    当前案例：{escape(verified_names)}
                </div>
            </article>
            <div class="wfz-scope-boundary">
                <strong>PRODUCT BOUNDARY / 产品边界</strong>
                <span>
                    本产品不是实时交易终端或商业金融数据库的替代品，不包含机构
                    内部路演与持仓资料，也不生成股价预测或买卖建议。
                </span>
            </div>
        </div>
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
            width="stretch",
        )


@st.cache_data(ttl=3600, max_entries=1, show_spinner=False)
def load_a_share_directory() -> pd.DataFrame:
    """Cache the public company directory for one hour."""
    return fetch_company_directory()


@st.cache_data(ttl=3600, max_entries=4, show_spinner=False)
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


@st.cache_data(ttl=600, max_entries=2, show_spinner=False)
def load_limit_up_pool(trade_date_text: str) -> pd.DataFrame:
    """Cache one recent daily limit-up pool for ten minutes."""
    return fetch_limit_up_pool(date.fromisoformat(trade_date_text))


@st.cache_data(ttl=3600, max_entries=4, show_spinner=False)
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


def _fetch_company_research_sources_concurrently(
    code: str,
    start_date_text: str,
    end_date_text: str,
    adjust: str,
) -> tuple[
    pd.DataFrame | None,
    pd.DataFrame | None,
    str | None,
    str | None,
]:
    """Fetch independent market and disclosure sources in parallel.

    The two public requests do not depend on each other.  Running them with a
    bounded two-worker pool reduces the first-run wall time from their sum to
    roughly the slower request while preserving separate failure messages.
    """
    start_date = date.fromisoformat(start_date_text)
    end_date = date.fromisoformat(end_date_text)
    with ThreadPoolExecutor(
        max_workers=2,
        thread_name_prefix="wfz-research",
    ) as executor:
        market_future = executor.submit(
            fetch_market_history,
            code,
            start_date,
            end_date,
            adjust=adjust,
        )
        announcement_future = executor.submit(
            fetch_announcements,
            code,
            start_date,
            end_date,
        )

        market_frame: pd.DataFrame | None = None
        announcement_frame: pd.DataFrame | None = None
        market_error: str | None = None
        announcement_error: str | None = None
        try:
            market_frame = market_future.result()
        except (DataSourceError, ValueError) as error:
            market_error = str(error)
        try:
            announcement_frame = announcement_future.result()
        except (DataSourceError, ValueError) as error:
            announcement_error = str(error)

    return (
        market_frame,
        announcement_frame,
        market_error,
        announcement_error,
    )


@st.cache_data(ttl=3600, max_entries=4, show_spinner=False)
def load_company_research_sources(
    code: str,
    start_date_text: str,
    end_date_text: str,
    adjust: str = "qfq",
) -> tuple[
    pd.DataFrame | None,
    pd.DataFrame | None,
    str | None,
    str | None,
]:
    """Cache one bounded parallel source bundle for company research."""
    return _fetch_company_research_sources_concurrently(
        code,
        start_date_text,
        end_date_text,
        adjust,
    )


@st.cache_data(ttl=1800, max_entries=1, show_spinner=False)
def load_official_annual_report(announcement_url: str) -> bytes:
    """Temporarily cache only the latest validated official PDF."""
    return download_official_pdf(announcement_url)


def show_compact_page_header(
    section: str,
    title: str,
    description: str,
) -> None:
    """Render a consistent subpage heading without repeating the home hero."""
    st.markdown(
        f"""
        <section class="wfz-page-intro">
            <div class="wfz-section-label">{escape(section)}</div>
            <h1>{escape(title)}</h1>
            <p>{escape(description)}</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _build_research_run_summary(
    elapsed_seconds: float,
    source_states: Mapping[str, bool],
) -> str:
    """Describe run time and source availability without implying quality."""
    source_summary = "｜".join(
        f"{label}：{'正常' if available else '暂不可用'}"
        for label, available in source_states.items()
    )
    return (
        f"本次处理用时 {elapsed_seconds:.1f} 秒｜数据链状态："
        f"{source_summary}。一小时内重复研究通常会复用缓存。"
    )


def _show_research_run_summary(
    elapsed_seconds: float,
    source_states: Mapping[str, bool],
) -> None:
    """Render one compact and consistent research-run receipt."""
    st.caption(
        _build_research_run_summary(elapsed_seconds, source_states)
    )


def _write_run_status(run_status: object | None, message: str) -> None:
    """Write a stage only when Streamlit created a live status container."""
    writer = getattr(run_status, "write", None)
    if callable(writer):
        writer(message)


def _update_run_status(
    run_status: object | None,
    *,
    label: str,
    state: str,
    expanded: bool,
) -> None:
    """Update live UI status while remaining safe in bare test mode."""
    updater = getattr(run_status, "update", None)
    if callable(updater):
        updater(label=label, state=state, expanded=expanded)


def show_product_footer() -> None:
    """Render the common developer attribution and product boundary."""
    st.markdown(
        """
        <div class="wfz-footer">
            <strong>FANGZHENG AI 金融研究实验室</strong> · 产品设计与研发：
            <strong>王方正 · Durham University</strong><br>
            通过剧情训练与真实公司研究培养有证据边界的金融判断；
            用于学习、求职演示与作品集展示，不构成投资建议。
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


def _browser_research_snapshot() -> dict[str, object]:
    """Return the small device-local state last received from the browser."""
    return normalise_browser_research_state(
        st.session_state.get("_wfz_browser_research_snapshot")
    )


def _queue_browser_research_command(
    action: str,
    company: CompanyIdentity,
    **payload: object,
) -> None:
    """Queue one idempotent browser-storage update for the next rerun."""
    command: dict[str, object] = {
        "id": f"{action}:{company['canonical_code']}:{time_ns()}",
        "action": action,
        "company": dict(company),
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    command.update(payload)
    st.session_state["_wfz_browser_research_command"] = command


def _sync_browser_research_state() -> None:
    """Synchronise bounded research history with this visitor's browser."""
    known_snapshot = _browser_research_snapshot()
    command = st.session_state.get("_wfz_browser_research_command")
    result = _BROWSER_RESEARCH_STORAGE(
        data={
            "storage_key": "wfz.research.v1",
            "max_recent": MAX_RECENT_RESEARCH,
            "max_watchlist": MAX_LOCAL_WATCHLIST,
            "max_evidence_checkpoints": MAX_EVIDENCE_CHECKPOINTS,
            "max_research_theses": MAX_RESEARCH_THESES,
            "known_snapshot": known_snapshot,
            "command": command,
        },
        default={"snapshot": known_snapshot},
        key="wfz_browser_research_storage",
        on_snapshot_change=lambda: None,
    )

    raw_snapshot = getattr(result, "snapshot", None)
    if raw_snapshot is None and isinstance(result, Mapping):
        raw_snapshot = result.get("snapshot")
    snapshot = normalise_browser_research_state(raw_snapshot)
    st.session_state["_wfz_browser_research_snapshot"] = snapshot

    if isinstance(command, Mapping) and (
        snapshot.get("last_command_id") == command.get("id")
    ):
        st.session_state.pop("_wfz_browser_research_command", None)


def _store_selected_company(company: CompanyIdentity) -> None:
    """Keep one company identity across every research subpage."""
    st.session_state["selected_company"] = dict(company)
    _queue_browser_research_command("record_research", company)


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


def _build_radar_research_context(
    row: ResearchQueueRow,
    *,
    scanned_on: date | None = None,
) -> dict[str, object]:
    """Keep only the evidence needed to explain why research was opened."""
    latest_disclosure = row["latest_disclosure"]
    return {
        "canonical_code": row["company"]["canonical_code"],
        "scan_date": (scanned_on or date.today()).isoformat(),
        "market_date": row["latest_date"],
        "research_priority": row["research_priority"],
        "radar_status": row["radar_status"],
        "triggered_signals": list(row["triggered_signals"]),
        "research_reasons": list(row["research_reasons"]),
        "disclosure_status": row["disclosure_status"],
        "latest_disclosure": (
            dict(latest_disclosure)
            if latest_disclosure is not None
            else None
        ),
    }


def _matching_radar_research_context(
    company: CompanyIdentity,
) -> Mapping[str, object] | None:
    """Return radar context only when it belongs to the selected company."""
    context = st.session_state.get(RADAR_RESEARCH_CONTEXT_KEY)
    if not isinstance(context, Mapping):
        return None
    if context.get("canonical_code") != company["canonical_code"]:
        return None
    return context


def _handoff_market_radar_to_comprehensive(
    row: ResearchQueueRow,
) -> None:
    """Carry one radar clue into a fresh, user-triggered comprehensive run."""
    company = row["company"]
    _store_selected_company(company)
    st.session_state[RADAR_RESEARCH_CONTEXT_KEY] = (
        _build_radar_research_context(row)
    )
    # A prior brief may describe an older run.  Clear only the rendered result;
    # the one-hour source cache can still make the next explicit run fast.
    st.session_state.pop(COMPREHENSIVE_BRIEF_KEY, None)
    st.session_state.pop(COMPREHENSIVE_ELAPSED_KEY, None)
    _switch_page("comprehensive")


def _show_radar_research_context(company: CompanyIdentity) -> None:
    """Explain the radar clue without presenting it as a conclusion."""
    context = _matching_radar_research_context(company)
    if context is None:
        return

    triggered_signals = context.get("triggered_signals", [])
    signal_text = (
        "、".join(str(item) for item in triggered_signals)
        if isinstance(triggered_signals, list) and triggered_signals
        else "未触发三项门槛"
    )
    research_reasons = context.get("research_reasons", [])
    reason_text = (
        "；".join(str(item) for item in research_reasons)
        if isinstance(research_reasons, list) and research_reasons
        else "等待综合研究重新核验"
    )

    with st.container(border=True):
        st.markdown("#### 🛰️ 本次研究由自选股雷达触发")
        summary_columns = st.columns(3)
        summary_columns[0].metric(
            "研究顺序",
            str(context.get("research_priority", "待核验")),
        )
        summary_columns[1].metric(
            "雷达状态",
            str(context.get("radar_status", "待核验")),
        )
        summary_columns[2].metric(
            "行情日期",
            str(context.get("market_date", "待核验")),
        )
        st.write(f"**雷达触发证据：** {signal_text}")
        st.write(f"**进入深度研究的原因：** {reason_text}。")

        latest_disclosure = context.get("latest_disclosure")
        if isinstance(latest_disclosure, Mapping):
            st.write(
                "**雷达已找到的最近官方公告：** "
                + str(latest_disclosure.get("title", "标题待核验"))
            )
            st.caption(
                f"{latest_disclosure.get('published_date', '日期待核验')}｜"
                f"{latest_disclosure.get('category', '类别待核验')}｜"
                f"关注程度：{latest_disclosure.get('attention', '待核验')}｜"
                f"{context.get('disclosure_status', '状态待核验')}｜"
                "综合研究仍会重新读取官方来源。"
            )
        else:
            st.caption(
                f"官方公告：{context.get('disclosure_status', '待核验')}。"
                "综合研究会再次尝试官方来源。"
            )

        st.caption(
            f"雷达扫描日：{context.get('scan_date', '待核验')}。"
            "以上内容只是本次研究的入口线索，不是投资结论；"
            "点击下方按钮后，综合 Agent 才会独立核验五条证据链。"
        )


def _render_company_search(
    *,
    key_prefix: str,
    navigate_on_success: bool,
    navigate_target: str = "company",
    auto_run_comprehensive: bool = False,
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
            width="stretch",
        )

    if submitted:
        # A valid six-digit code and the small verified demonstration list can
        # be resolved locally.  Do not make every user wait for the full live
        # A-share directory when it cannot improve that result.
        matches = resolve_company(query, None)
        if not matches and str(query).strip():
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
            if auto_run_comprehensive:
                _execute_comprehensive_research(company)
            if navigate_on_success:
                _switch_page(navigate_target)
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
            width="stretch",
            key=f"{key_prefix}_confirm_company",
        ):
            company = options[selection]
            _store_selected_company(company)
            if auto_run_comprehensive:
                _execute_comprehensive_research(company)
            if navigate_on_success:
                _switch_page(navigate_target)
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

    snapshot = _browser_research_snapshot()
    watchlist_codes = {
        item["canonical_code"]
        for item in snapshot["watchlist"]
        if isinstance(item, Mapping) and "canonical_code" in item
    }
    is_saved = company["canonical_code"] in watchlist_codes
    action_columns = st.columns(2)
    if action_columns[0].button(
        "★ 已加入本机自选股（点击移除）"
        if is_saved
        else "☆ 加入本机自选股",
        key=f"toggle_local_watchlist_{company['canonical_code']}",
        width="stretch",
    ):
        _queue_browser_research_command("toggle_watchlist", company)
        st.rerun()
    if action_columns[1].button(
        "更换研究公司",
        key=f"change_company_{company['canonical_code']}",
        width="stretch",
    ):
        st.session_state.pop("selected_company", None)
        _switch_page("research_terminal")


def _render_local_research_hub() -> None:
    """Show device-local recent research and a five-company watchlist."""
    snapshot = _browser_research_snapshot()
    recent = snapshot["recent"]
    watchlist = snapshot["watchlist"]
    watchlist_codes = {
        item["canonical_code"]
        for item in watchlist
        if isinstance(item, Mapping) and "canonical_code" in item
    }

    st.markdown(
        '<div class="wfz-section-label">'
        "我的研究入口 · STORED ON THIS DEVICE"
        "</div>",
        unsafe_allow_html=True,
    )
    recent_column, watchlist_column = st.columns(2)
    with recent_column:
        st.subheader("最近研究")
        if not recent:
            st.caption("研究过的公司会自动出现在这里，最多保留6家。")
        for item in recent:
            if not isinstance(item, Mapping):
                continue
            canonical_code = str(item["canonical_code"])
            company = dict(item)
            row_columns = st.columns([3, 2])
            if row_columns[0].button(
                f"继续研究｜{item['name']} · {item['code']}",
                width="stretch",
                key=f"recent_open_{canonical_code}",
            ):
                _store_selected_company(company)  # type: ignore[arg-type]
                _switch_page("comprehensive")
            is_saved = canonical_code in watchlist_codes
            if row_columns[1].button(
                "★ 移出自选" if is_saved else "☆ 加入自选",
                width="stretch",
                key=f"recent_watchlist_{canonical_code}",
            ):
                _queue_browser_research_command(
                    "toggle_watchlist",
                    company,  # type: ignore[arg-type]
                )
                st.rerun()

    with watchlist_column:
        st.subheader(f"我的自选股｜{len(watchlist)}/{MAX_LOCAL_WATCHLIST}")
        if not watchlist:
            st.caption("可从最近研究或公司页面加入，最多保存5家。")
        for item in watchlist:
            if not isinstance(item, Mapping):
                continue
            canonical_code = str(item["canonical_code"])
            company = dict(item)
            row_columns = st.columns([3, 1])
            if row_columns[0].button(
                f"研究｜{item['name']} · {item['code']}",
                width="stretch",
                key=f"watchlist_open_{canonical_code}",
            ):
                _store_selected_company(company)  # type: ignore[arg-type]
                _switch_page("comprehensive")
            if row_columns[1].button(
                "移除",
                width="stretch",
                key=f"watchlist_remove_{canonical_code}",
            ):
                _queue_browser_research_command(
                    "toggle_watchlist",
                    company,  # type: ignore[arg-type]
                )
                st.rerun()

    if snapshot["storage_status"] == "unavailable":
        st.warning(
            "当前浏览器限制了本机存储，这些记录暂时只能保留在本次访问中。"
        )
    else:
        st.caption(
            "这些记录只保存在当前浏览器，不上传姓名、联系方式、年报文件或"
            "其他个人数据；清理浏览器网站数据后记录会被删除。"
        )


def _format_percent(value: float | None) -> str:
    """Format an optional ratio without disguising missing evidence as zero."""
    return "数据不足" if value is None else f"{value:.1%}"


def _format_optional_cny_100m(value: float | None) -> str:
    """Format one optional RMB amount without turning missing data into zero."""
    return "数据不足" if value is None else f"¥{value / 100_000_000:,.2f}亿"


def _format_percentage_point_change(value: float | None) -> str | None:
    """Format a ratio difference as percentage points, not growth."""
    if value is None:
        return None
    return f"较上年 {value * 100:+.1f}个百分点"


def _format_multiple_change(value: float | None) -> str | None:
    """Format the change in a multiple without positive/negative colouring."""
    if value is None:
        return None
    return f"较上年 {value:+.2f}倍"


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
    with st.expander(
        "查看成交量与换手率的历史位置",
        expanded=True,
    ):
        percentile_columns = st.columns(2)
        percentile_columns[0].metric(
            "成交量历史分位",
            _format_percent(activity["volume_percentile_250d"]),
            (
                f"比较前{activity['volume_percentile_sessions']}个有效交易日"
            ),
            delta_color="off",
        )
        percentile_columns[1].metric(
            "普通换手率历史分位",
            _format_percent(activity["turnover_percentile_250d"]),
            (
                "比较前"
                f"{activity['turnover_percentile_sessions']}个有效交易日"
            ),
            delta_color="off",
        )
        st.caption(
            "分位只使用当前交易日之前最多250个有效交易日，"
            "至少需要20个样本；50%表示接近历史样本中间位置，"
            "数值越高只代表相对更活跃，不代表未来涨跌。"
            "换手率分位仍基于普通换手率，不等同于有效换手率。"
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


def _show_market_anomaly_report(
    report: MarketAnomalyReport,
) -> None:
    """Render the Agent synthesis without turning anomalies into advice."""
    st.subheader("Agent 综合结论")
    if report["status"] == "compound_anomaly":
        st.warning(f"**{report['headline']}**\n\n{report['conclusion']}")
    elif report["status"] == "single_anomaly":
        st.info(f"**{report['headline']}**\n\n{report['conclusion']}")
    elif report["status"] == "insufficient_data":
        st.warning(f"**{report['headline']}**\n\n{report['conclusion']}")
    else:
        st.info(f"**{report['headline']}**\n\n{report['conclusion']}")

    status_labels = {
        "triggered": "触发",
        "not_triggered": "未触发",
        "unavailable": "证据不足",
    }
    columns = st.columns(3)
    for column, signal in zip(
        columns,
        report["signals"],
        strict=True,
    ):
        with column:
            with st.container(border=True):
                st.markdown(f"#### {signal['name']}")
                st.markdown(
                    f"**状态：{status_labels[signal['status']]}**"
                )
                st.write(signal["evidence"])
                st.caption(signal["limitation"])

    st.info(report["next_step"])
    st.caption(
        f"数据截止：{report['as_of_date']}｜"
        f"可判断 {report['available_signal_count']}/3 项｜"
        f"触发 {report['triggered_signal_count']} 项｜"
        f"最近候选日期 {report['recent_event_count']} 个。"
    )
    st.warning(report["limitation"])


def _show_anomaly_event_research(
    events: list[MarketActivityEvent],
    company: CompanyIdentity,
    announcements: pd.DataFrame | None,
    *,
    history_events: list[MarketActivityEvent] | None = None,
    market_source: str = "公开行情适配器",
    turnover_source: str = "公开行情字段或暂未取得",
) -> None:
    """Connect one selected anomaly candidate to point-in-time evidence."""
    st.subheader("候选日期与官方证据链")
    st.caption(
        "自动扫描最近250个交易日：成交量达到此前20日中位数2倍，"
        "日涨幅达到板块规则参考阈值，或普通换手率达到此前历史"
        "90%分位时进入列表。结果只用于选择研究日期，不是买卖信号。"
    )
    if not events:
        st.info("最近扫描范围内没有发现符合当前门槛的异常交易日。")
        return

    event_options = {
        f"{event['date']}｜{event['event_type']}": event
        for event in events
    }
    selected_label = st.selectbox(
        "选择一个候选日期",
        options=list(event_options),
        key=f"anomaly_event_{company['canonical_code']}",
    )
    selected = event_options[selected_label]

    with st.container(border=True):
        st.markdown(
            f"#### {selected['date']}｜{selected['event_type']}"
        )
        columns = st.columns(4)
        columns[0].metric("当日收盘", f"¥{selected['close']:,.2f}")
        columns[1].metric(
            "日涨跌幅",
            _format_percent(selected["daily_return"]),
        )
        volume_ratio = selected["volume_ratio_20d"]
        columns[2].metric(
            "成交量 / 前20日中位数",
            "数据不足" if volume_ratio is None else f"{volume_ratio:.2f}倍",
        )
        columns[3].metric(
            "普通换手率",
            _format_percent(selected["turnover"]),
        )
        st.caption(
            f"涨跌幅口径：{selected['daily_return_basis']}｜"
            "成交量历史分位："
            f"{_format_percent(selected['volume_percentile_250d'])}｜"
            "普通换手率历史分位："
            f"{_format_percent(selected['turnover_percentile_250d'])}。"
        )

    evidence_chain: EventEvidenceChain | None = None
    if announcements is None:
        st.warning(
            "官方公告源暂时不可访问。异动数字仍可核验，"
            "但系统不会使用新闻或未经核验内容替代官方公告。"
        )
    else:
        evidence_chain = build_event_evidence_chain(
            _announcement_evidence_records(announcements),
            selected["date"],
        )
        _show_event_evidence_chain(
            evidence_chain,
            event_context=selected["event_type"],
        )

    analogs = find_historical_anomaly_analogs(
        selected,
        history_events or events,
    )
    st.markdown("#### 历史相似异动｜规则匹配")
    st.caption(
        "只比较所选日期以前的信号组合、日涨跌幅、成交量倍数和"
        "普通换手率历史分位；缺失项不会按0处理。相似度不是未来"
        "涨跌预测，也不构成投资建议。"
    )
    if not analogs:
        st.info(
            "当前扫描范围内没有具备足够可比字段的更早异动日期。"
        )
    else:
        for rank, analog in enumerate(analogs, start=1):
            with st.container(border=True):
                title_column, score_column = st.columns([3, 1])
                title_column.markdown(
                    f"**{rank}. {analog['date']}｜"
                    f"{analog['event_type']}**"
                )
                score_column.metric(
                    "规则相似度",
                    f"{analog['similarity_score']:.0%}",
                )
                volume_ratio = analog["volume_ratio_20d"]
                volume_ratio_text = (
                    "数据不足"
                    if volume_ratio is None
                    else f"{volume_ratio:.2f}倍"
                )
                st.caption(
                    f"日涨跌幅 {_format_percent(analog['daily_return'])}｜"
                    "成交量 / 前20日中位数 "
                    f"{volume_ratio_text}"
                    "｜普通换手率历史分位 "
                    f"{_format_percent(analog['turnover_percentile_250d'])}"
                    f"｜可比维度 {analog['comparable_dimension_count']} 项。"
                )
                st.write(analog["comparison_summary"])
                if st.button(
                    "用这个日期进入 Historical Lens",
                    width="stretch",
                    key=(
                        f"anomaly_analog_{company['code']}_"
                        f"{selected['date']}_{analog['date']}"
                    ),
                ):
                    st.session_state["historical_prefill_date"] = (
                        analog["date"]
                    )
                    st.session_state["historical_prefill_context"] = (
                        f"与 {selected['date']} 规则相似："
                        f"{analog['event_type']}"
                    )
                    _switch_page("historical")

    report_html = build_anomaly_report_card_html(
        company,
        selected,
        evidence_chain,
        market_source=market_source,
        turnover_source=turnover_source,
        analogs=analogs,
        historical_lens_url=(
            "https://fangzhengai.wang/render_historical_lens_page"
        ),
    )
    st.markdown("#### 保存本次研究")
    st.caption(
        "下载文件可离线打开，并可通过浏览器“打印”另存为 PDF；"
        "报告保留数据来源、公告链接和时间隔离说明。"
    )
    st.download_button(
        "下载异动研究报告（HTML）",
        data=report_html.encode("utf-8"),
        file_name=(
            f"WFZ_{company['code']}_{selected['date']}_异动研究报告.html"
        ),
        mime="text/html",
        width="stretch",
        key=f"anomaly_report_{company['code']}_{selected['date']}",
    )

    action_columns = st.columns(2)
    if action_columns[0].button(
        "进入 Historical Lens 完整复盘",
        type="primary",
        width="stretch",
        key=(
            f"anomaly_historical_{company['code']}_{selected['date']}"
        ),
    ):
        st.session_state["historical_prefill_date"] = selected["date"]
        st.session_state["historical_prefill_context"] = (
            selected["event_type"]
        )
        _switch_page("historical")
    if action_columns[1].button(
        "查看完整K线",
        width="stretch",
        key=f"anomaly_market_{company['code']}",
    ):
        _switch_page("market")

    with st.expander("查看扫描方法与限制"):
        st.write(
            "成交量基准只使用目标日期之前20个交易日，不把目标日自身"
            "放进中位数。涨停候选优先使用公开行情源的涨跌幅字段；"
            "字段缺失时才用页面所选价格口径的相邻收盘价计算。"
        )
        st.write(
            "历史分位只使用每个异常日之前最多250个有效交易日，"
            "至少需要20个样本；不会把目标日自身或未来交易日放入比较。"
            "普通换手率达到历史90%分位才进入候选；"
            "它仍不等同于有效换手率。"
        )
        st.write(
            "新股上市初期、重新上市、退市整理首日和其他无涨跌幅限制"
            "情形仍需交易所数据复核。进入 Historical Lens 后，公告仍按"
            "公开日期过滤，扫描结果不会绕过时间隔离。"
        )


def _load_company_research_data(
    company: CompanyIdentity,
) -> tuple[pd.DataFrame | None, MarketMetrics | None, pd.DataFrame | None]:
    """Load market history and announcements independently and safely."""
    end_date = date.today()
    research_start = end_date - timedelta(
        days=DEFAULT_RESEARCH_LOOKBACK_DAYS
    )
    market_frame: pd.DataFrame | None = None
    metrics: MarketMetrics | None = None
    announcements: pd.DataFrame | None = None
    market_frame, announcements, _, _ = load_company_research_sources(
        company["code"],
        research_start.isoformat(),
        end_date.isoformat(),
        "qfq",
    )
    if market_frame is not None and not market_frame.empty:
        try:
            metrics = calculate_market_metrics(market_frame)
        except ValueError:
            metrics = None
    return market_frame, metrics, announcements


def _run_comprehensive_research(
    company: CompanyIdentity,
) -> ComprehensiveResearchBrief:
    """Run five independent research lanes without hiding source failures."""
    end_date = date.today()
    start_date = end_date - timedelta(days=DEFAULT_RESEARCH_LOOKBACK_DAYS)
    data_errors: list[str] = []
    market_frame: pd.DataFrame | None = None
    market_metrics: MarketMetrics | None = None
    market_activity: MarketActivityEvidence | None = None
    market_source = "公开行情适配器"
    turnover_source = "暂未取得"

    (
        market_frame,
        announcement_frame,
        market_error,
        announcement_error,
    ) = load_company_research_sources(
        company["code"],
        start_date.isoformat(),
        end_date.isoformat(),
        "qfq",
    )

    if market_error:
        data_errors.append(f"行情证据链：{market_error}")
    elif market_frame is not None:
        try:
            market_metrics = calculate_market_metrics(market_frame)
            market_activity = calculate_market_activity(
                market_frame,
                company,
            )
        except ValueError as error:
            data_errors.append(f"行情证据链：{error}")
        market_source = str(
            market_frame.attrs.get("source", market_source)
        )
        turnover_source = str(
            market_frame.attrs.get("turnover_source", turnover_source)
        )

    announcements: list[Mapping[str, object]] | None
    announcements_status = ""
    if announcement_error:
        announcements = None
        announcements_status = "官方公告源本次未完成核验"
        data_errors.append(f"官方公告证据链：{announcement_error}")
    elif announcement_frame is not None:
        announcements = announcement_frame.to_dict("records")
        announcements_status = f"已核验公告 {len(announcements)} 条"
    else:
        announcements = None
        announcements_status = "官方公告源本次未完成核验"

    latest_annual_report: Mapping[str, object] | None = None
    if announcement_frame is not None:
        try:
            selected_report = select_latest_annual_report(announcement_frame)
        except ValueError as error:
            data_errors.append(f"年度报告定位证据链：{error}")
        else:
            if selected_report is not None:
                latest_annual_report = selected_report.to_dict()

    financial_history = None
    if company["code"] in verified_financial_history_codes():
        try:
            records = load_verified_financial_history(company["code"])
            financial_history = select_financial_history_as_of(
                records,
                end_date,
            )
        except ValueError as error:
            data_errors.append(f"财务历史证据链：{error}")

    # Reuse only a compact same-company result already created by the user.
    # The comprehensive run must not download and parse another large PDF.
    financial_snapshot: Mapping[str, object] | None = None
    stored_snapshot = st.session_state.get("on_demand_financial_snapshot")
    if isinstance(stored_snapshot, Mapping):
        snapshot_company = stored_snapshot.get("company")
        if (
            isinstance(snapshot_company, Mapping)
            and snapshot_company.get("canonical_code")
            == company["canonical_code"]
        ):
            financial_snapshot = stored_snapshot

    return build_comprehensive_research_brief(
        company,
        market_metrics=market_metrics,
        market_activity=market_activity,
        market_source=market_source,
        turnover_source=turnover_source,
        announcements=announcements,
        announcements_status=announcements_status,
        latest_annual_report=latest_annual_report,
        financial_history=financial_history,
        financial_snapshot=financial_snapshot,
        generated_on=end_date,
        data_errors=data_errors,
    )


def _show_research_conclusion_card(
    brief: ComprehensiveResearchBrief,
) -> None:
    """Show the ranked first-pass conclusion before detailed evidence."""
    conclusion = brief["conclusion"]
    primary_key = conclusion["primary_key"]
    with st.container(border=True):
        st.caption("公司研究结论卡 · FIRST-PASS RESEARCH")
        st.markdown("## 当前最值得关注")
        if primary_key == "evidence_gap":
            st.error(conclusion["headline"])
        elif primary_key in {"no_rule_triggered", "initial_research"}:
            st.info(conclusion["headline"])
        else:
            st.warning(conclusion["headline"])
        st.write(conclusion["explanation"])

        st.markdown("#### 财务、市场与官方动态")
        pillar_columns = st.columns(3)
        for column, pillar in zip(
            pillar_columns,
            conclusion["pillars"],
            strict=True,
        ):
            with column:
                with st.container(border=True):
                    st.markdown(f"**{pillar['label']}**")
                    if pillar["state"] == "attention":
                        st.warning(pillar["status_label"])
                    elif pillar["state"] == "clear":
                        st.info(pillar["status_label"])
                    else:
                        st.error(pillar["status_label"])
                    st.write(pillar["summary"])
                    st.caption(f"依据：{pillar['basis']}")

        question_column, evidence_column = st.columns([3, 2])
        with question_column:
            st.markdown("**下一步最值得核验的问题**")
            st.write(conclusion["next_question"])
        with evidence_column:
            st.markdown("**本次证据状态**")
            st.write(conclusion["evidence_summary"])
        st.caption(
            "这是研究阅读顺序，不是公司评分、上涨概率或买卖建议。"
        )


def _show_comprehensive_research_brief(
    brief: ComprehensiveResearchBrief,
) -> None:
    """Display one evidence-first research run and its audit trail."""
    status_labels = {
        "verified": "已核验",
        "partial": "部分证据",
        "unavailable": "暂不可用",
    }
    _show_research_conclusion_card(brief)
    st.markdown("### 详细证据与分析")
    st.markdown("#### 综合研究状态")
    summary_columns = st.columns(4)
    summary_columns[0].metric(
        "证据覆盖率",
        f"{brief['coverage_ratio']:.0%}",
    )
    summary_columns[1].metric("覆盖状态", brief["coverage_label"])
    summary_columns[2].metric(
        "已核验证据链",
        f"{brief['verified_lane_count']} / 5",
    )
    summary_columns[3].metric(
        "确定性观察",
        f"{len(brief['findings'])} 项",
    )
    st.progress(
        brief["coverage_ratio"],
        text=(
            "这里衡量本次取得的数据范围，不代表公司质量、"
            "上涨概率或结论正确概率。"
        ),
    )

    st.markdown("#### 五条证据链")
    evidence_lanes = brief["evidence_lanes"]
    for start in range(0, len(evidence_lanes), 3):
        batch = evidence_lanes[start : start + 3]
        columns = st.columns(len(batch))
        for column, lane in zip(columns, batch, strict=True):
            with column:
                with st.container(border=True):
                    st.markdown(f"**{lane['label']}**")
                    if lane["status"] == "verified":
                        st.success(status_labels[lane["status"]])
                    elif lane["status"] == "partial":
                        st.warning(status_labels[lane["status"]])
                    else:
                        st.error(status_labels[lane["status"]])
                    st.write(lane["summary"])
                    st.caption(
                        f"来源：{lane['source']}｜"
                        f"截止：{lane['as_of_date'] or '不适用'}"
                    )
                    st.caption(lane["limitation"])
                    if lane["source_url"]:
                        st.link_button(
                            "查看官方证据 ↗",
                            lane["source_url"],
                            width="stretch",
                        )

    st.markdown("#### 确定性研究观察")
    if not brief["findings"]:
        st.warning(
            "当前证据不足，系统没有使用旧样例或 AI 猜测生成观察。"
        )
    for index, finding in enumerate(brief["findings"], start=1):
        with st.container(border=True):
            heading_column, status_column = st.columns([4, 1])
            heading_column.markdown(
                f"**{index}. {finding['category']}｜"
                f"{finding['headline']}**"
            )
            status_column.caption(status_labels[finding["status"]])
            st.write(finding["statement"])
            st.caption(f"依据：{finding['basis']}")
            if finding["source_url"]:
                st.link_button("查看对应官方原文 ↗", finding["source_url"])

    company = brief["company"]
    report_html = build_comprehensive_research_report_html(
        brief,
        radar_context=_matching_radar_research_context(company),
    )
    audit_payload = build_comprehensive_research_audit_payload(
        brief,
        radar_context=_matching_radar_research_context(company),
    )
    st.markdown("#### 保存本次综合研究")
    report_column, audit_column = st.columns(2)
    with report_column:
        st.download_button(
            "下载综合研究简报（HTML）",
            data=report_html.encode("utf-8"),
            file_name=(
                f"WFZ_{company['code']}_{brief['generated_on']}_"
                "综合研究简报.html"
            ),
            mime="text/html",
            width="stretch",
            key=f"comprehensive_report_{company['canonical_code']}",
        )
    with audit_column:
        st.download_button(
            "下载可审计数据包（JSON）",
            data=json.dumps(
                audit_payload,
                ensure_ascii=False,
                indent=2,
            ),
            file_name=(
                f"WFZ_{company['code']}_{brief['generated_on']}_"
                "综合研究审计包.json"
            ),
            mime="application/json",
            width="stretch",
            key=f"comprehensive_audit_{company['canonical_code']}",
        )
    st.caption(
        "HTML 适合离线阅读或打印为 PDF；JSON 保留同一份证据、"
        "执行轨迹、雷达来源和 SHA-256 证据指纹，便于系统复核。"
    )

    st.markdown("#### 下一步核验任务")
    action_columns = st.columns(2)
    for index, action in enumerate(brief["actions"]):
        with action_columns[index % 2]:
            if st.button(
                f"P{action['priority']}｜{action['label']}",
                width="stretch",
                key=(
                    f"comprehensive_action_{company['code']}_"
                    f"{action['page']}"
                ),
            ):
                _switch_page(action["page"])
            st.caption(action["reason"])

    with st.expander("查看 Agent 执行轨迹与失败隔离", expanded=False):
        for step in brief["trace"]:
            st.markdown(
                f"**{step['sequence']:02d}｜{step['agent']}｜"
                f"{status_labels[step['status']]}**"
            )
            st.write(step["task"])
            st.caption(step["output"])

    with st.expander("查看研究限制", expanded=True):
        for limitation in brief["limitations"]:
            st.write(f"- {limitation}")


def _execute_comprehensive_research(company: CompanyIdentity) -> None:
    """Run and store one brief before navigation or after manual refresh."""
    # Never show a previous company's brief while the new run is starting.
    st.session_state.pop(COMPREHENSIVE_BRIEF_KEY, None)
    st.session_state.pop(COMPREHENSIVE_ELAPSED_KEY, None)
    started_at = perf_counter()
    with st.status(
        "正在并行读取行情与官方公告……",
        expanded=True,
    ) as run_status:
        st.write("公司身份已确认，正在同时执行两条外部数据链。")
        brief_result = _run_comprehensive_research(company)
        st.write("公开数据读取完成，正在生成证据覆盖与核验任务。")
        elapsed_seconds = perf_counter() - started_at
        run_status.update(
            label=f"综合研究已完成｜用时 {elapsed_seconds:.1f} 秒",
            state="complete",
            expanded=False,
        )
    st.session_state[COMPREHENSIVE_BRIEF_KEY] = brief_result
    st.session_state[COMPREHENSIVE_ELAPSED_KEY] = elapsed_seconds


def render_comprehensive_research_page() -> None:
    """Render the one-click coordinator across existing research modules."""
    apply_product_theme()
    show_compact_page_header(
        "旗舰 / 一键综合研究 · COMPREHENSIVE AGENT",
        "一键综合研究 Agent",
        "输入一家中国上市公司，自动串联行情、交易活跃度、官方公告、"
        "年度报告与财务证据，生成可下载、可追溯的研究简报。多年已核验"
        "数据优先；普通公司可复用当前会话的单期财务快照。",
    )
    company = _selected_company()
    if company is None:
        st.info("请先选择一家研究公司。")
        _render_company_search(
            key_prefix="comprehensive",
            navigate_on_success=False,
            auto_run_comprehensive=True,
        )
        company = _selected_company()
    if company is None:
        show_product_footer()
        return

    _show_company_banner(company)
    _show_radar_research_context(company)
    st.info(
        "这次运行按需读取公开数据，不会提前下载全市场资料；"
        "某个来源失败时，其他证据链仍会继续，并明确标记缺口。"
        "综合研究不会重复解析大型PDF；如需单期财务数据，请先生成"
        "财务快照再重新运行。"
    )
    brief = st.session_state.get(COMPREHENSIVE_BRIEF_KEY)
    has_matching_brief = isinstance(brief, dict) and brief.get(
        "company", {}
    ).get("canonical_code") == company["canonical_code"]
    manual_run_requested = st.button(
        (
            "重新运行并刷新公开数据"
            if has_matching_brief
            else "运行一键综合研究 Agent"
        ),
        type="primary",
        width="stretch",
        key=f"run_comprehensive_{company['canonical_code']}",
    )
    if manual_run_requested:
        _execute_comprehensive_research(company)

    brief = st.session_state.get(COMPREHENSIVE_BRIEF_KEY)
    if not isinstance(brief, dict) or brief.get("company", {}).get(
        "canonical_code"
    ) != company["canonical_code"]:
        st.caption(
            "点击运行后，本页会生成五条证据链、确定性观察、"
            "Agent 执行轨迹和下一步核验任务。"
        )
        show_product_footer()
        return

    _show_comprehensive_research_brief(brief)  # type: ignore[arg-type]
    elapsed_seconds = st.session_state.get(COMPREHENSIVE_ELAPSED_KEY)
    if isinstance(elapsed_seconds, (int, float)):
        st.caption(
            f"本次综合研究用时 {elapsed_seconds:.1f} 秒；一小时内重复研究"
            "同一家公司通常会直接复用缓存。"
        )
    show_product_footer()


def render_home_page() -> None:
    """Render the platform home with two clear primary modules."""
    apply_product_theme()
    show_platform_identity()
    show_platform_modules()
    st.info(
        "研究员任务局负责学习与能力训练；公司研究终端负责真实公开资料的"
        "检索、计算和核验。游戏中的开放调查会逐步连接研究终端，但不会"
        "把研究结果包装成股价预测或买卖建议。"
    )
    show_product_footer()


def _start_historical_game_mission() -> None:
    """Open the one cross-module investigation at its earliest search date."""
    mission = HISTORICAL_GAME_MISSION
    company = build_company_identity(
        mission["company_code"],
        mission["company_name"],
    )
    _store_selected_company(company)
    st.session_state["historical_game_mission_id"] = mission["mission_id"]
    saved_answer = st.session_state.get("historical_game_mission_answer")
    st.session_state["historical_prefill_date"] = (
        str(saved_answer)
        if saved_answer
        else mission["initial_date"].isoformat()
    )
    st.session_state["historical_prefill_context"] = (
        "研究员任务局｜开放调查01"
    )
    _switch_page("historical")


def _render_cash_evidence_node(player_name: str) -> None:
    """Render the changing office search and exact evidence-chain check."""
    evidence_completed = (
        st.session_state.get("cash_case_stage") == "evidence_completed"
    )
    attempt_index = int(
        st.session_state.get("cash_evidence_attempt_index", 0)
    )
    evidence_case = build_cash_evidence_case(attempt_index)

    st.divider()
    st.caption("案件调查 · EVIDENCE ROOM 02")
    st.subheader("第二节点：办公室里的六份材料")
    with st.container(border=True):
        st.markdown(f"#### 调查员 {escape(player_name)}，项目办公室已解锁")
        st.write(
            "系统不会告诉你哪份材料是线索、证据或干扰项。请打开不同"
            "位置找到的文件，阅读日期、条款、签章、金额和证据来源，再"
            "选择恰好4份材料组成证据链。"
        )
        st.caption(
            f"动态卷宗第 {evidence_case['attempt_number']} 版｜报告截止日："
            f"{evidence_case['reporting_date'].isoformat()}｜答错不扣生命，"
            "但会更换客户、金额、付款期限和材料顺序。"
        )

    document_columns = st.columns(2)
    option_labels: dict[str, str] = {}
    for index, document in enumerate(evidence_case["documents"]):
        document_label = (
            f"{index + 1}. {document['location']}｜{document['title']}"
        )
        option_labels[document_label] = document["document_id"]
        with document_columns[index % 2]:
            with st.expander(
                f"📁 {document['location']}｜{document['title']}"
            ):
                st.caption(document["document_type"])
                st.write(document["body"])
                st.caption(document["footer"])

    feedback = st.session_state.pop("cash_evidence_feedback", None)
    if isinstance(feedback, str):
        st.warning(feedback)

    if not evidence_completed:
        with st.form(
            key=f"cash_evidence_form_{evidence_case['case_id']}",
            border=True,
        ):
            st.markdown("#### 提交你的证据链")
            st.write(evidence_case["question"])
            selected_labels = st.multiselect(
                "选择恰好4份材料",
                options=list(option_labels),
                max_selections=4,
                placeholder="阅读文件后再选择，不要只看标题",
                key=f"cash_evidence_selection_{evidence_case['case_id']}",
            )
            evidence_submitted = st.form_submit_button(
                "提交证据链",
                type="primary",
                width="stretch",
            )

        if evidence_submitted:
            if len(selected_labels) != 4:
                st.warning("证据链必须包含恰好4份材料。请继续搜索和取舍。")
                return
            selected_ids = [
                option_labels[label] for label in selected_labels
            ]
            evaluation = evaluate_cash_evidence_selection(
                evidence_case,
                selected_ids,
            )
            if evaluation["is_correct"]:
                st.session_state["cash_case_stage"] = "evidence_completed"
                st.session_state["cash_evidence_explanation"] = evidence_case[
                    "explanation"
                ]
                st.rerun()
            else:
                st.session_state["cash_evidence_attempt_index"] = (
                    attempt_index + 1
                )
                st.session_state["cash_evidence_feedback"] = (
                    f"{evaluation['feedback']} 没有扣除生命；办公室卷宗已经"
                    "更换，请重新阅读，不能沿用上一轮的文件编号。"
                )
                st.rerun()
        return

    st.success("第二节点完成｜你已经把线索整理成一条可相互核验的证据链。")
    explanation = str(
        st.session_state.get("cash_evidence_explanation", "")
    )
    if explanation:
        with st.container(border=True):
            st.markdown("#### 审查官证据复盘")
            st.write(explanation)
            st.caption(
                "结论边界：本卷宗能够解释这一项业务的时间差，不能据此"
                "推断其他客户、其他期间或整家公司的现金质量。"
            )
    st.info(
        "证据已经找齐，但研究工作还没有结束。正式答辩不会重复问你"
        "哪四份文件，而会换成新的公司情境，检查你能否形成结论、守住"
        "边界，并提出下一步核验行动。"
    )
    if st.button(
        "进入审查委员会｜开始三轮结论答辩",
        type="primary",
        width="stretch",
        key="start_cash_defense",
    ):
        st.session_state["cash_case_stage"] = "defense"
        st.session_state["cash_defense_lives"] = 3
        st.session_state["cash_defense_round_index"] = 0
        st.session_state["cash_defense_attempt_index"] = 0
        st.session_state["cash_defense_completed_explanations"] = []
        st.session_state.pop("cash_defense_feedback", None)
        st.rerun()


def _render_cash_defense_node(player_name: str) -> None:
    """Render the three-round formal defence with one shared life pool."""
    stage = str(st.session_state.get("cash_case_stage", "defense"))
    lives = int(st.session_state.get("cash_defense_lives", 3))
    round_index = int(st.session_state.get("cash_defense_round_index", 0))
    attempt_index = int(
        st.session_state.get("cash_defense_attempt_index", 0)
    )

    st.divider()
    st.caption("正式考核 · REVIEW COMMITTEE 03")
    st.subheader("第三节点：三轮结论答辩")

    if stage == "defense_failed":
        st.error("本轮三次容错机会已经用完｜案件退回重新调查。")
        with st.container(border=True):
            st.markdown(f"#### 调查员 {escape(player_name)}，委员会暂不签字")
            st.write(
                "你保留调查员代号和已学内容，但不能沿用上一套文件与"
                "答案。返回办公室后，系统会更换客户、金额、期限和材料"
                "顺序；重新组成证据链，才能再次进入答辩。"
            )
        if st.button(
            "返回办公室｜领取全新调查卷宗",
            type="primary",
            width="stretch",
            key="restart_cash_evidence_after_defense",
        ):
            st.session_state["cash_case_stage"] = "evidence"
            st.session_state["cash_evidence_attempt_index"] = (
                int(st.session_state.get("cash_evidence_attempt_index", 0))
                + 1
            )
            st.session_state.pop("cash_evidence_explanation", None)
            st.session_state.pop("cash_defense_feedback", None)
            st.rerun()
        return

    if stage in {"case_completed", "migration_completed"}:
        st.success("《消失的现金》前三节点通过｜委员会接受你的研究判断。")
        with st.container(border=True):
            st.markdown(f"#### 调查员 {escape(player_name)}的答辩记录")
            for explanation in st.session_state.get(
                "cash_defense_completed_explanations",
                [],
            ):
                st.write(f"- {explanation}")
            st.caption(
                "你证明的不是会背一个结论，而是能在新材料中区分事实、"
                "风险、判断边界和下一步行动。"
            )
        return

    question = build_cash_defense_question(round_index, attempt_index)
    life_display = "❤️" * lives + "🩶" * (3 - lives)
    with st.container(border=True):
        st.markdown(f"#### {life_display}　剩余 {lives} 次容错机会")
        st.caption(
            f"第 {question['round_number']} / 3 轮｜"
            f"{question['round_title']}｜动态答辩卷第"
            f" {question['attempt_number']} 版"
        )
        st.write(
            "三轮共用三条生命。未选择答案不会扣生命；答错会扣除一次"
            "机会，并立即换成新的公司和证据，不能记忆上一题。"
        )

    feedback = st.session_state.pop("cash_defense_feedback", None)
    if isinstance(feedback, str):
        st.warning(feedback)

    with st.form(
        key=f"cash_defense_form_{question['question_id']}",
        border=True,
    ):
        st.markdown(f"#### 新案卷｜{question['company_name']}")
        st.caption("委员会只确认以下材料，不允许添加题外假设：")
        for evidence_item in question["evidence_items"]:
            st.write(f"- {evidence_item}")
        st.markdown(f"**{question['prompt']}**")
        selected_option = st.radio(
            "选择唯一最严谨的答辩意见",
            options=question["options"],
            index=None,
            key=f"cash_defense_answer_{question['question_id']}",
        )
        submitted = st.form_submit_button(
            "向委员会提交意见",
            type="primary",
            width="stretch",
        )

    if not submitted:
        return
    if selected_option is None:
        st.warning("请先选择一项答辩意见。空白提交不会扣除生命。")
        return
    if selected_option == question["correct_option"]:
        completed_explanations = list(
            st.session_state.get(
                "cash_defense_completed_explanations",
                [],
            )
        )
        completed_explanations.append(question["explanation"])
        st.session_state["cash_defense_completed_explanations"] = (
            completed_explanations
        )
        if round_index == 2:
            st.session_state["cash_case_stage"] = "case_completed"
        else:
            st.session_state["cash_defense_round_index"] = round_index + 1
            st.session_state["cash_defense_attempt_index"] = attempt_index + 1
            st.session_state["cash_defense_feedback"] = (
                f"第{round_index + 1}轮通过。{question['explanation']}"
            )
        st.rerun()

    remaining_lives = lives - 1
    st.session_state["cash_defense_lives"] = remaining_lives
    st.session_state["cash_defense_attempt_index"] = attempt_index + 1
    if remaining_lives <= 0:
        st.session_state["cash_case_stage"] = "defense_failed"
    else:
        st.session_state["cash_defense_feedback"] = (
            "这项意见没有同时尊重证据和判断边界，已扣除一次容错机会。"
            "委员会已经换成新公司与新证据，请重新推理。"
        )
    st.rerun()


def _render_cash_case_first_node() -> None:
    """Teach and practise the first profit-versus-cash reasoning node."""
    st.divider()
    st.caption("案件序章 · PLAYABLE CASE 01")
    st.subheader("《消失的现金》｜第一节点：利润不等于现金")

    player_name = str(st.session_state.get("game_player_name", "")).strip()
    if not player_name:
        st.write(
            "进入案件前，请为主人公设置一个调查员代号。它只保存在当前"
            "浏览器会话，用于剧情称呼；请不要填写身份证号、电话或其他"
            "敏感信息。"
        )
        with st.form("game_player_identity_form", border=True):
            entered_name = st.text_input(
                "调查员代号",
                placeholder="例如：方正、北辰、Lin",
                max_chars=12,
            )
            identity_submitted = st.form_submit_button(
                "建立角色档案并进入案件",
                type="primary",
                width="stretch",
            )
        if identity_submitted:
            normalised_name = " ".join(entered_name.strip().split())
            if not normalised_name:
                st.error("请先填写一个调查员代号。")
                return
            st.session_state["game_player_name"] = normalised_name
            st.session_state["cash_case_stage"] = "briefing"
            st.session_state["cash_case_attempt_index"] = 0
            st.rerun()
        return

    stage = str(st.session_state.get("cash_case_stage", "briefing"))
    with st.container(border=True):
        st.caption("22:17 · FANGZHENG AI 调查部")
        st.markdown(f"#### 调查员 {escape(player_name)}，第一份案卷已经送达")
        st.write(
            "岚桥智能报告显示：利润增长38%，经营现金流却下降22%。"
            "有人据此断言公司一定造假，也有人认为利润增长就代表现金"
            "充足。你的第一项任务不是选边站，而是先弄清两种数字各自在"
            "回答什么问题。"
        )

    teaching_columns = st.columns(3)
    with teaching_columns[0].container(border=True):
        st.caption("01 / PROFIT")
        st.markdown("#### 利润看什么？")
        st.write(
            "利润先问：这段期间完成了多少业务、为这些业务承担了多少"
            "成本。符合确认条件的收入，不必等客户真正付款后才进入利润。"
        )
    with teaching_columns[1].container(border=True):
        st.caption("02 / CASH")
        st.markdown("#### 现金看什么？")
        st.write(
            "现金只问：钱在什么时候真正进入或离开账户。已经确认的收入"
            "如果尚未收款，会形成应收款，但不会变成本月收到的现金。"
        )
    with teaching_columns[2].container(border=True):
        st.caption("03 / JUDGEMENT")
        st.markdown("#### 差异代表什么？")
        st.write(
            "利润与现金不一致是一条调查线索，不是自动定罪。还要检查合同、"
            "验收、回款期限、应收账款和期后收款，才能解释差异。"
        )

    if stage == "briefing":
        st.info(
            "记住两个问题：利润看“业务是否完成”，现金看“钱是否真的"
            "收付”。准备好后进入引导练习。"
        )
        if st.button(
            "我理解了，打开第一份业务档案",
            type="primary",
            width="stretch",
            key="cash_case_start_practice",
        ):
            st.session_state["cash_case_stage"] = "practice"
            st.rerun()
        return

    feedback = st.session_state.pop("cash_case_feedback", None)
    if isinstance(feedback, str):
        st.warning(feedback)

    if stage == "practice":
        attempt_index = int(
            st.session_state.get("cash_case_attempt_index", 0)
        )
        question = build_cash_timing_question(attempt_index)
        with st.form(
            key=f"cash_case_question_{question['question_id']}",
            border=True,
        ):
            st.caption(
                f"动态业务档案 · 第 {question['attempt_number']} 份｜"
                "本节点答错不扣生命"
            )
            st.markdown("#### 分别计算利润影响与现金影响")
            st.write(question["prompt"])
            selected_option = st.radio(
                "选择最准确的计算结果",
                options=question["options"],
                index=None,
                key=f"cash_case_answer_{question['question_id']}",
            )
            answer_submitted = st.form_submit_button(
                "提交判断",
                type="primary",
                width="stretch",
            )

        if answer_submitted:
            if selected_option is None:
                st.warning("请先选择一个答案，再提交判断。")
            elif selected_option == question["correct_option"]:
                st.session_state["cash_case_stage"] = "timing_completed"
                st.session_state["cash_case_last_explanation"] = question[
                    "explanation"
                ]
                st.rerun()
            else:
                st.session_state["cash_case_attempt_index"] = (
                    attempt_index + 1
                )
                st.session_state["cash_case_feedback"] = (
                    "这次计算还没有同时分清“确认了多少业务”和“实际收付"
                    "了多少钱”。没有扣除生命；档案数据已经更换，请用同一"
                    "方法重新判断，不能背上一题的答案。"
                )
                st.rerun()
        return

    explanation = str(
        st.session_state.get("cash_case_last_explanation", "")
    )
    st.success("第一教学节点完成｜利润与现金的两只计量表已经分开。")
    if explanation:
        with st.container(border=True):
            st.markdown("#### 审查官复盘")
            st.write(explanation)
    if stage in {"completed", "timing_completed"}:
        st.info(
            "你现在只证明自己掌握了基础计算。下一节点会把合同、应收"
            "明细、验收文件和期后回款放进同一办公室，要求你自己寻找"
            "材料并判断差异是否值得警惕。"
        )
        if st.button(
            "进入项目办公室｜开始证据调查",
            type="primary",
            width="stretch",
            key="open_cash_evidence_room",
        ):
            st.session_state["cash_case_stage"] = "evidence"
            st.session_state["cash_evidence_attempt_index"] = 0
            st.rerun()
        return

    if stage in {"evidence", "evidence_completed"}:
        _render_cash_evidence_node(player_name)

    if stage in {
        "defense",
        "defense_failed",
        "case_completed",
        "migration_completed",
    }:
        _render_cash_defense_node(player_name)


def render_game_hub_page() -> None:
    """Introduce the game learning loop before the first playable case."""
    apply_product_theme()
    show_compact_page_header(
        "模块一 / 沉浸式金融研究训练",
        "研究员任务局",
        "先在故事中理解金融概念，再进入调查、证据拼接和结论答辩。"
        "真正的难度来自材料阅读、时间判断和证据边界，而不是文字陷阱。",
    )
    st.markdown(
        """
        <div class="wfz-learning-loop">
            <div class="wfz-learning-step">01｜教学</div>
            <div class="wfz-learning-step">02｜练习</div>
            <div class="wfz-learning-step">03｜调查</div>
            <div class="wfz-learning-step">04｜证据链</div>
            <div class="wfz-learning-step">05｜答辩</div>
            <div class="wfz-learning-step">06｜迁移</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    mission_completed = (
        st.session_state.get("historical_game_mission_completed")
        == HISTORICAL_MISSION_ID
    )
    case_column, progression_column = st.columns([1.35, 1])
    with case_column.container(border=True):
        st.caption("首个教学案件 · CASE 01")
        st.subheader("《消失的现金》")
        st.write(
            "一家虚构公司的利润增长38%，经营现金流却下降22%。玩家将先"
            "理解利润与现金的区别，再阅读合同、验收、应收账款、银行流水"
            "和期后材料，判断差异意味着什么、又不能证明什么。"
        )
        if mission_completed:
            st.success(
                "首案六阶段完整通关：你已经把虚构卷宗中的方法迁移到"
                "真实历史证据。"
            )
        else:
            st.success(
                "前三节点已开放：零基础讲解、六份材料调查，以及三轮动态"
                "结论答辩。"
            )
    with progression_column.container(border=True):
        st.caption("成长路径 · SEQUENTIAL PROGRESSION")
        st.subheader("不能跳关，但可以真正成长")
        st.write(
            "完成基础教学后，系统会逐步减少提示。最终进入真实历史开放案件，"
            "玩家只获得研究问题与时间截点，需要自行使用公司研究终端寻找"
            "证据，并接受审查官追问。"
        )
        if mission_completed:
            st.progress(
                1.0,
                text="首案六阶段完整通关｜下一步制作荣誉档案",
            )
        else:
            st.progress(
                0.48,
                text="教学、证据调查与三轮答辩可玩｜下一步完成迁移关",
            )

    _render_cash_case_first_node()

    st.divider()
    with st.container(border=True):
        mission = HISTORICAL_GAME_MISSION
        st.caption("跨模块开放调查 · ONE DELIBERATE TOOL MISSION")
        st.subheader(mission["title"])
        st.markdown(f"**案卷：{mission['case_file']}**")
        st.write(mission["question"])
        st.caption(
            f"调查区间：{mission['window_start'].isoformat()} — "
            f"{mission['window_end'].isoformat()}。进入 Historical Lens 后，"
            "拖动时点滑轨并比较相邻日期；页面不会直接标出答案。"
        )
        st.info(
            "这类“离开游戏、调用真实研究工具、再带回结论”的任务只安排"
            "一次。它考查时间边界，不考股价预测，也不扣除三条生命。"
        )
        if mission_completed:
            st.success(
                "开放调查已完成｜你已经区分证据时钟与行情时钟，并守住"
                "后续市场观察的归因边界。"
            )
        defense_completed = st.session_state.get("cash_case_stage") in {
            "case_completed",
            "migration_completed",
        }
        mission_label = "通过三轮结论答辩后解锁 Historical Lens"
        if mission_completed:
            mission_label = "重新查看调查证据"
        elif defense_completed:
            mission_label = "开始开放调查｜进入 Historical Lens"
        if st.button(
            mission_label,
            type="primary" if defense_completed else "secondary",
            disabled=not defense_completed and not mission_completed,
            width="stretch",
            key="start_historical_game_mission",
        ):
            _start_historical_game_mission()

    st.warning(
        "教学、练习和引导调查不扣生命。三条生命只在正式结论答辩中"
        "启用；三轮共用生命，答错立即更换案件，三次失败退回重新调查。"
    )
    show_product_footer()


def render_research_terminal_page() -> None:
    """Render the primary entry page for real-company research tools."""
    apply_product_theme()
    show_product_identity()
    show_chinese_user_guide()

    show_home_value_proposition()
    show_home_capabilities()
    if st.button(
        "进入研究工具导航｜按任务查看全部功能",
        width="stretch",
        key="home_to_research_workspace",
    ):
        _switch_page("workspace")

    st.markdown(
        '<div class="wfz-section-label">'
        "开始研究 · START RESEARCH"
        "</div>",
        unsafe_allow_html=True,
    )
    st.header("输入公司名称或股票代码")
    st.write(
        "点击“开始研究”后，系统会核验上市公司身份，并直接生成"
        "一页式研究结论；结论连接官方披露、年报证据与历史市场数据。"
        "普通功能不依赖付费AI额度。"
    )
    _render_company_search(
        key_prefix="home",
        navigate_on_success=True,
        navigate_target="comprehensive",
        auto_run_comprehensive=True,
    )
    discovery_columns = st.columns(3)
    if discovery_columns[0].button(
        "打开每日涨停板观察台",
        type="primary",
        width="stretch",
        key="home_to_limit_up_board",
    ):
        _switch_page("limit_up")
    if discovery_columns[1].button(
        "打开自选股研究任务队列",
        width="stretch",
        key="home_to_market_radar",
    ):
        _switch_page("radar")
    if discovery_columns[2].button(
        "打开横向比较工作台",
        width="stretch",
        key="home_to_cross_company_comparison",
    ):
        _switch_page("comparison")
    st.caption(
        "还没有确定单一研究对象？先查看公开涨停股池，"
        "输入最多5个股票代码比较市场异动，或使用已核验年报做"
        "共同年度横向比较。"
    )

    st.divider()
    show_home_research_scope()

    st.divider()
    _render_local_research_hub()

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


def render_research_workspace_page() -> None:
    """Group all research tools by the job the user needs to complete."""
    apply_product_theme()
    show_compact_page_header(
        "公司研究终端 / 工具导航 · RESEARCH WORKSPACE",
        "按研究问题选择工具",
        "全部功能被组织成五个相互衔接的集合：先发现或选择标的，"
        "再完成公司总览，随后根据问题进入市场、财务或证据核验。",
    )

    company = _selected_company()
    if company is None:
        st.info(
            "尚未选择研究公司。可以先输入公司名称或代码，也可以直接从"
            "“标的发现与跟踪”开始。"
        )
        _render_company_search(
            key_prefix="workspace",
            navigate_on_success=False,
        )
    else:
        _show_company_banner(company)

    st.markdown(
        '<div class="wfz-section-label">'
        "五个研究集合 · FIVE CONNECTED COLLECTIONS"
        "</div>",
        unsafe_allow_html=True,
    )
    st.write(
        "推荐主线：**选择标的 → 综合研究 → 发现问题 → 专项核验 → "
        "形成可复核底稿**。每个专项页面都服务于这条主线，而不是独立存在。"
    )

    collections = (
        {
            "title": "01｜标的发现与跟踪",
            "description": (
                "还没有确定研究对象，或需要管理已经关注的公司时使用。"
            ),
            "flow": "涨停板发现候选 → 自选股队列安排研究优先级",
            "tools": (
                ("查看每日涨停板观察台", "limit_up"),
                ("扫描自选股任务队列", "radar"),
            ),
        },
        {
            "title": "02｜单家公司研究主线",
            "description": (
                "已经确定公司，希望先建立身份、行情、公告和年报的整体认识。"
            ),
            "flow": (
                "公司概览 → 一键汇总五条证据链 → 核验新证据 → "
                "更新研究假设"
            ),
            "tools": (
                ("打开公司研究中心", "company"),
                ("运行一键综合研究 Agent", "comprehensive"),
                ("核验上次研究后的新证据", "evidence_delta"),
                ("维护研究结论账本", "thesis_ledger"),
            ),
        },
        {
            "title": "03｜市场行为与历史复盘",
            "description": (
                "需要判断价格、成交和换手发生了什么，并检查当时有哪些公开信息。"
            ),
            "flow": "K线 → 成交与换手 → 异动识别 → 回到历史时点复盘",
            "tools": (
                ("查看K线与市场表现", "market"),
                ("分析成交量与换手率", "volume_turnover"),
                ("进入市场异动 Agent", "anomaly"),
                ("使用 Historical Lens 复盘", "historical"),
            ),
        },
        {
            "title": "04｜财务报表与经营证据",
            "description": (
                "需要从年报原文核验财务变化、跨年趋势、公司差异或异常原因。"
            ),
            "flow": "年报原文 → 多年趋势 → 横向比较 → 异常解释",
            "tools": (
                ("生成全市场按需财务快照", "financial_snapshot"),
                ("进入年报与证据分析", "annual"),
                ("打开财务趋势实验室", "financial_trend"),
                ("进行跨公司横向比较", "comparison"),
                ("解释财务异常", "financial_anomaly"),
            ),
        },
        {
            "title": "05｜证据质量与数据扩展",
            "description": (
                "需要了解数据边界、核验规则，或把新公司安全加入深度案例库。"
            ),
            "flow": "自动生成候选数据 → 人工审批 → 公开方法与局限",
            "tools": (
                ("扩展已核验公司目录", "onboarding"),
                ("查看方法、证据与产品边界", "methodology"),
            ),
        },
    )

    workspace_columns = st.columns(2)
    for index, collection in enumerate(collections):
        with workspace_columns[index % 2].container(border=True):
            st.markdown(f"### {collection['title']}")
            st.write(collection["description"])
            st.caption(f"建议顺序：{collection['flow']}。")
            for label, target in collection["tools"]:
                if st.button(
                    label,
                    width="stretch",
                    key=f"workspace_to_{target}",
                ):
                    _switch_page(target)

    st.warning(
        "各集合用于组织研究流程，不代表评分、选股结果或买卖建议。"
        "如果证据不足，专项页面会保留缺口并建议下一项核验任务。"
    )
    show_product_footer()


def _evidence_checkpoint_for(
    company: CompanyIdentity,
) -> Mapping[str, object] | None:
    """Return this company's validated device-local evidence checkpoint."""
    snapshot = _browser_research_snapshot()
    for checkpoint in snapshot["evidence_checkpoints"]:
        if (
            isinstance(checkpoint, Mapping)
            and checkpoint.get("canonical_code")
            == company["canonical_code"]
        ):
            return checkpoint
    return None


def _show_evidence_delta_review(review: EvidenceDeltaReview) -> None:
    """Render one deterministic disclosure-change result."""
    window = review["window"]
    metric_columns = st.columns(4)
    metric_columns[0].metric("本次官方公告", review["total_count"])
    metric_columns[1].metric("高关注公告", review["high_attention_count"])
    metric_columns[2].metric(
        "财务与业绩",
        review["group_counts"]["财务与业绩"],
    )
    metric_columns[3].metric(
        "治理与风险",
        review["group_counts"]["治理与风险"],
    )

    st.caption(
        f"核验范围：{window['start_date'].isoformat()} 至 "
        f"{window['end_date'].isoformat()}｜模式：{window['mode']}。"
    )
    if window["truncated"]:
        st.warning(
            "上次核验距今超过365天。为控制公开接口请求量，本次只核验最近"
            "365天；更早区间仍是明确的数据缺口。"
        )
    if review["item_limit_reached"]:
        st.warning(
            "本页和下载简报最多保留最近100条公告；总数仍按全部已核验"
            "记录计算。"
        )

    if not review["items"]:
        st.info("本次范围内没有找到通过官方域名校验的公告。")
    else:
        st.subheader("按研究问题归类的证据变化")
        for group, count in review["group_counts"].items():
            if not count:
                continue
            with st.expander(f"{group}｜{count} 条", expanded=group in {
                "财务与业绩",
                "治理与风险",
            }):
                group_items = [
                    item
                    for item in review["items"]
                    if item["evidence_group"] == group
                ]
                for item in group_items[:20]:
                    with st.container(border=True):
                        st.markdown(f"**{item['title']}**")
                        st.caption(
                            f"{item['published_date'].isoformat()}｜"
                            f"{item['delta_status']}｜原类别："
                            f"{item['source_category']}｜关注程度："
                            f"{item['attention']}"
                        )
                        st.link_button(
                            "查看官方原文",
                            item["source_url"],
                        )
                if len(group_items) > 20:
                    st.caption(
                        f"页面先展示20条；下载简报还包含本次保留的其余 "
                        f"{len(group_items) - 20} 条。该类别共核验 {count} 条。"
                    )

    report_html = build_evidence_delta_report_html(review)
    company = review["company"]
    st.download_button(
        "下载证据变化简报（HTML）",
        data=report_html,
        file_name=(
            f"{company['code']}_{company['name']}_证据变化简报_"
            f"{review['generated_on'].isoformat()}.html"
        ),
        mime="text/html",
        width="stretch",
    )


def render_evidence_delta_page() -> None:
    """Compare official disclosures with a device-local research checkpoint."""
    apply_product_theme()
    show_compact_page_header(
        "03 / 证据增量 · EVIDENCE DELTA",
        "证据增量 Agent",
        "再次研究同一家公司时，只核验上次检查后出现的官方披露，并把"
        "变化归入财务、经营、资本运作和治理风险等研究问题。",
    )
    company = _selected_company()
    if company is None:
        st.warning("请先选择要持续跟踪的上市公司。")
        company = _render_company_search(
            key_prefix="evidence_delta",
            navigate_on_success=False,
        )
    if company is None:
        show_product_footer()
        return

    _show_company_banner(company)
    checkpoint = _evidence_checkpoint_for(company)
    checked_at = (
        checkpoint.get("evidence_checked_at")
        if checkpoint is not None
        else None
    )
    window = build_evidence_window(
        checked_at,
        as_of_date=date.today(),
    )
    if checked_at:
        st.success(f"本机上次证据核验时间：{checked_at}")
        st.caption(
            "为了避免漏掉上次核验当天晚些时候发布的公告，本次会重新包含"
            "该日期，并把这些记录标为“同日待复核”。"
        )
    else:
        st.info(
            "当前浏览器还没有这家公司的证据基准。首次运行会核验最近30天，"
            "成功后可保存为下次比较起点。"
        )

    notice = st.session_state.pop("_wfz_evidence_checkpoint_notice", None)
    if isinstance(notice, str):
        st.success(notice)

    result_key = f"_wfz_evidence_delta_result_{company['canonical_code']}"
    if st.button(
        "核验上次研究后的官方证据",
        type="primary",
        width="stretch",
        key=f"run_evidence_delta_{company['canonical_code']}",
    ):
        st.session_state.pop(result_key, None)
        try:
            with st.spinner("正在按时间窗口核验官方公告……"):
                announcements = load_company_announcements(
                    company["code"],
                    window["start_date"].isoformat(),
                    window["end_date"].isoformat(),
                )
                review = build_evidence_delta_review(
                    company,
                    announcements.to_dict("records"),
                    window=window,
                    generated_on=date.today(),
                )
                del announcements
                gc.collect()
        except (DataSourceError, ValueError) as error:
            st.error(f"官方公告源本次未完成核验：{error}")
            st.info("系统不会用新闻摘要、历史缓存或AI猜测填补这次失败。")
        else:
            st.session_state[result_key] = review

    review = st.session_state.get(result_key)
    if isinstance(review, dict):
        _show_evidence_delta_review(review)  # type: ignore[arg-type]
        if st.button(
            "保存本次成功核验为下次基准",
            width="stretch",
            key=f"save_evidence_delta_{company['canonical_code']}",
        ):
            _queue_browser_research_command(
                "save_evidence_checkpoint",
                company,
            )
            st.session_state["_wfz_evidence_checkpoint_notice"] = (
                "已请求把本次成功核验时间保存到当前浏览器；页面刷新后生效。"
            )
            st.rerun()

    snapshot = _browser_research_snapshot()
    if snapshot["storage_status"] == "unavailable":
        st.warning(
            "当前浏览器禁止本机存储，基准只能在本次访问中短暂保留。"
        )
    else:
        st.caption(
            f"每台设备最多保存 {MAX_EVIDENCE_CHECKPOINTS} 家公司的核验基准；"
            "不保存姓名、联系方式、公告正文或年报文件，也不占用Render数据库。"
        )
    st.warning(
        "公告分类和关注程度用于安排阅读顺序，不预测股价，也不代表利好、"
        "利空或买卖建议。"
    )
    if st.button(
        "把新证据带入研究结论账本",
        width="stretch",
        key=f"evidence_delta_to_thesis_{company['canonical_code']}",
    ):
        _switch_page("thesis_ledger")
    show_product_footer()


def _research_theses_for(
    company: CompanyIdentity,
) -> list[Mapping[str, object]]:
    """Return this company's validated device-local research theses."""
    snapshot = _browser_research_snapshot()
    return [
        thesis
        for thesis in snapshot["research_theses"]
        if isinstance(thesis, Mapping)
        and thesis.get("canonical_code") == company["canonical_code"]
    ]


def _latest_evidence_items_for(
    company: CompanyIdentity,
) -> list[Mapping[str, object]]:
    """Reuse only the latest in-session Evidence Delta result."""
    result = st.session_state.get(
        f"_wfz_evidence_delta_result_{company['canonical_code']}"
    )
    if not isinstance(result, Mapping):
        return []
    result_company = result.get("company")
    if (
        not isinstance(result_company, Mapping)
        or result_company.get("canonical_code") != company["canonical_code"]
    ):
        return []
    items = result.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, Mapping)]


def _iso_date(value: object) -> str:
    """Return a small ISO date string for one validated evidence item."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()[:10]


def render_research_thesis_page() -> None:
    """Maintain human-reviewed hypotheses against official evidence."""
    apply_product_theme()
    show_compact_page_header(
        "04 / 研究结论账本 · THESIS LEDGER",
        "研究结论账本",
        "把研究假设、支持条件、失效条件和官方新证据放在同一条可追溯"
        "记录中。系统只匹配主题，证据方向和结论状态必须由用户确认。",
    )
    company = _selected_company()
    if company is None:
        st.warning("请先选择要建立研究结论账本的上市公司。")
        company = _render_company_search(
            key_prefix="thesis_ledger",
            navigate_on_success=False,
        )
    if company is None:
        show_product_footer()
        return

    _show_company_banner(company)
    notice = st.session_state.pop("_wfz_thesis_ledger_notice", None)
    if isinstance(notice, str):
        st.success(notice)

    theses = _research_theses_for(company)
    counts = thesis_status_counts(theses)
    metric_columns = st.columns(4)
    for column, status in zip(metric_columns, THESIS_STATUSES):
        column.metric(status, counts[status])

    st.subheader("建立一条可证伪的研究假设")
    st.caption(
        "不要只写“公司很好”。同时写清楚什么公开证据会支持它，以及出现"
        "什么情况时应放弃或修改它。"
    )
    with st.form(
        f"create_thesis_{company['canonical_code']}",
        clear_on_submit=True,
    ):
        hypothesis = st.text_area(
            "研究假设",
            max_chars=240,
            placeholder=(
                "例如：公司收入增长能够转化为持续的经营现金流改善。"
            ),
        )
        topic = st.selectbox("对应研究主题", THESIS_TOPICS)
        confirmation = st.text_area(
            "支持条件",
            max_chars=360,
            placeholder=(
                "例如：连续两个报告期经营现金流增速不低于收入增速，"
                "且应收账款占收入比例未明显上升。"
            ),
        )
        invalidation = st.text_area(
            "失效条件",
            max_chars=360,
            placeholder=(
                "例如：利润增长但经营现金流持续下降，或应收账款增速"
                "长期显著高于收入增速。"
            ),
        )
        create_submitted = st.form_submit_button(
            "保存研究假设到当前浏览器",
            type="primary",
            width="stretch",
        )
    if create_submitted:
        if not all(
            value.strip()
            for value in (hypothesis, confirmation, invalidation)
        ):
            st.error("研究假设、支持条件和失效条件都需要填写。")
        else:
            _queue_browser_research_command(
                "save_research_thesis",
                company,
                thesis_id=f"{company['canonical_code']}:{time_ns()}",
                hypothesis=hypothesis,
                confirmation_criteria=confirmation,
                invalidation_criteria=invalidation,
                topic=topic,
            )
            st.session_state["_wfz_thesis_ledger_notice"] = (
                "已请求把研究假设保存到当前浏览器；页面刷新后生效。"
            )
            st.rerun()

    evidence_items = _latest_evidence_items_for(company)
    if evidence_items:
        st.info(
            f"已连接本次会话中最近一次证据增量结果，共 "
            f"{len(evidence_items)} 条官方公告。账本只按主题匹配，"
            "不会自动判断支持或反驳。"
        )
    else:
        st.info(
            "当前会话还没有这家公司的证据增量结果。可以先建立假设，"
            "再去证据增量 Agent 核验最新官方公告。"
        )
        if st.button(
            "先去核验官方新证据",
            width="stretch",
            key=f"thesis_to_evidence_delta_{company['canonical_code']}",
        ):
            _switch_page("evidence_delta")

    st.subheader(f"当前公司研究假设｜{len(theses)} 条")
    if not theses:
        st.caption("还没有保存研究假设。先完成上面的三项输入即可建立第一条。")

    for thesis in theses:
        thesis_id = str(thesis["thesis_id"])
        safe_key = thesis_id.replace(":", "_").replace(".", "_")
        matches = matching_evidence_items(thesis, evidence_items)
        with st.container(border=True):
            st.caption(
                f"{thesis['topic']}｜人工状态：{thesis['status']}｜"
                f"最后更新：{thesis['updated_at']}"
            )
            st.markdown(f"### {thesis['hypothesis']}")
            criteria_columns = st.columns(2)
            with criteria_columns[0]:
                st.markdown("**支持条件**")
                st.write(thesis["confirmation_criteria"])
            with criteria_columns[1]:
                st.markdown("**失效条件**")
                st.write(thesis["invalidation_criteria"])

            if thesis.get("review_note"):
                st.markdown(f"**最近人工复核：** {thesis['review_note']}")
            if thesis.get("evidence_url"):
                st.caption(
                    f"已引用官方证据：{thesis.get('evidence_date', '')}｜"
                    f"{thesis.get('evidence_title', '')}"
                )
                st.link_button(
                    "查看已引用的官方原文",
                    str(thesis["evidence_url"]),
                )

            if matches:
                st.markdown("**最近主题匹配证据｜方向待人工判断**")
                for item in matches:
                    st.caption(
                        f"{_iso_date(item.get('published_date'))}｜"
                        f"{item.get('title', '')}"
                    )

            evidence_labels = ["不引用官方证据"]
            evidence_by_label: dict[str, Mapping[str, object]] = {}
            for index, item in enumerate(matches, start=1):
                label = (
                    f"{index}｜{_iso_date(item.get('published_date'))}｜"
                    f"{str(item.get('title', ''))[:80]}"
                )
                evidence_labels.append(label)
                evidence_by_label[label] = item

            with st.form(f"review_thesis_{safe_key}"):
                current_status = str(thesis["status"])
                status = st.selectbox(
                    "人工复核状态",
                    THESIS_STATUSES,
                    index=THESIS_STATUSES.index(current_status),
                    key=f"thesis_status_{safe_key}",
                )
                review_note = st.text_area(
                    "复核备注",
                    value=str(thesis.get("review_note", "")),
                    max_chars=360,
                    placeholder=(
                        "说明为什么支持、为什么出现反方证据，或还缺少什么。"
                    ),
                    key=f"thesis_note_{safe_key}",
                )
                evidence_label = st.selectbox(
                    "引用本次主题匹配的官方证据（可选）",
                    evidence_labels,
                    key=f"thesis_evidence_{safe_key}",
                )
                review_submitted = st.form_submit_button(
                    "保存人工复核",
                    width="stretch",
                )
            if review_submitted:
                evidence = evidence_by_label.get(evidence_label)
                _queue_browser_research_command(
                    "update_research_thesis",
                    company,
                    thesis_id=thesis_id,
                    status=status,
                    review_note=review_note,
                    evidence_title=(
                        str(evidence.get("title", "")) if evidence else ""
                    ),
                    evidence_url=(
                        str(evidence.get("source_url", ""))
                        if evidence else ""
                    ),
                    evidence_date=(
                        _iso_date(evidence.get("published_date"))
                        if evidence else ""
                    ),
                )
                st.session_state["_wfz_thesis_ledger_notice"] = (
                    "已请求保存人工复核结果；页面刷新后生效。"
                )
                st.rerun()

            if st.button(
                "删除这条研究假设",
                key=f"delete_thesis_{safe_key}",
            ):
                _queue_browser_research_command(
                    "delete_research_thesis",
                    company,
                    thesis_id=thesis_id,
                )
                st.session_state["_wfz_thesis_ledger_notice"] = (
                    "已请求从当前浏览器删除这条研究假设。"
                )
                st.rerun()

    report_html = build_thesis_ledger_report_html(
        company,
        theses,
        generated_on=date.today(),
    )
    st.download_button(
        "下载研究结论账本（HTML）",
        data=report_html,
        file_name=(
            f"{company['code']}_{company['name']}_研究结论账本_"
            f"{date.today().isoformat()}.html"
        ),
        mime="text/html",
        width="stretch",
        disabled=not theses,
    )

    snapshot = _browser_research_snapshot()
    if snapshot["storage_status"] == "unavailable":
        st.warning("当前浏览器禁止本机存储，账本无法跨访问保留。")
    else:
        st.caption(
            f"每台设备最多保存 {MAX_RESEARCH_THESES} 条研究假设。记录持久化"
            "在当前浏览器；为显示和导出，内容会进入当前应用会话，但不会写入"
            "服务器数据库。清除本站浏览数据后记录会消失。"
        )
    st.warning(
        "请勿填写客户资料、持仓、未公开信息或其他敏感内容。主题匹配不代表"
        "支持、反驳、利好或利空；账本不构成投资建议。"
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
    started_at = perf_counter()
    with st.status(
        "正在同时读取公开行情与官方公告……",
        expanded=True,
    ) as run_status:
        market_frame, metrics, announcements = _load_company_research_data(
            company
        )
        _write_run_status(
            run_status,
            "行情指标已完成计算。"
            if metrics is not None
            else "行情数据链本次未完成，其他功能继续。"
        )
        _write_run_status(
            run_status,
            f"官方公告已完成核验，共 {len(announcements)} 条。"
            if announcements is not None
            else "官方公告数据链本次未完成，行情结果继续展示。"
        )
        elapsed_seconds = perf_counter() - started_at
        available_count = sum(
            (metrics is not None, announcements is not None)
        )
        _update_run_status(
            run_status,
            label=(
                f"公司研究数据同步完成｜{available_count}/2 条数据链可用｜"
                f"{elapsed_seconds:.1f} 秒"
            ),
            state="complete" if available_count else "error",
            expanded=False,
        )

    _show_research_run_summary(
        elapsed_seconds,
        {
            "公开行情": metrics is not None,
            "官方公告": announcements is not None,
        },
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

    action_columns = st.columns(5)
    if action_columns[0].button(
        "运行综合研究 Agent",
        width="stretch",
        type="primary",
    ):
        _switch_page("comprehensive")
    if action_columns[1].button(
        "查看完整K线与市场表现",
        width="stretch",
    ):
        _switch_page("market")
    if action_columns[2].button(
        "进入市场异动 Agent",
        width="stretch",
    ):
        _switch_page("anomaly")
    if action_columns[3].button(
        "进入 Historical Lens",
        width="stretch",
    ):
        _switch_page("historical")
    if action_columns[4].button(
        "进入年报与证据分析",
        width="stretch",
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
    research_columns = st.columns(2)
    if research_columns[0].button(
        "进入成交量与换手率研究",
        type="primary",
        width="stretch",
        key=f"market_to_volume_turnover_{company['canonical_code']}",
    ):
        _switch_page("volume_turnover")
    if research_columns[1].button(
        "进入市场异动 Agent 查看候选日期",
        width="stretch",
        key=f"market_to_anomaly_{company['canonical_code']}",
    ):
        _switch_page("anomaly")

    figure = _build_kline_figure(market_frame, company)
    st.plotly_chart(
        figure,
        width="stretch",
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


def _build_volume_turnover_figure(
    history: pd.DataFrame,
    company: CompanyIdentity,
) -> object:
    """Plot bounded participation ratios without exposing ambiguous units."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    figure = make_subplots(specs=[[{"secondary_y": True}]])
    figure.add_trace(
        go.Bar(
            x=history["date"],
            y=history["volume_ratio_20d"],
            name="成交量 / 前20日中位数",
            marker_color="#3577a8",
            opacity=0.72,
            hovertemplate="%{x}<br>成交量倍数 %{y:.2f}x<extra></extra>",
        ),
        secondary_y=False,
    )
    figure.add_trace(
        go.Scatter(
            x=history["date"],
            y=history["ordinary_turnover"],
            mode="lines+markers",
            name="普通换手率",
            line={"color": "#c28a24", "width": 2},
            marker={"size": 4},
            hovertemplate="%{x}<br>普通换手率 %{y:.2%}<extra></extra>",
        ),
        secondary_y=True,
    )
    figure.add_hline(
        y=1,
        line_dash="dot",
        line_color="rgba(53, 119, 168, 0.55)",
        annotation_text="前20日中位数",
        secondary_y=False,
    )
    figure.update_layout(
        title=(
            f"{company['name']}｜最近 {len(history)} 个交易日量能结构"
        ),
        height=520,
        margin={"l": 20, "r": 20, "t": 58, "b": 20},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,0.72)",
        hovermode="x unified",
        legend={"orientation": "h", "y": 1.08, "x": 0},
    )
    figure.update_yaxes(
        title_text="成交量倍数",
        rangemode="tozero",
        secondary_y=False,
    )
    figure.update_yaxes(
        title_text="普通换手率",
        tickformat=".1%",
        rangemode="tozero",
        secondary_y=True,
    )
    return figure


def _show_effective_turnover_verification(
    snapshot: VolumeTurnoverSnapshot,
) -> None:
    """Offer a manual, provenance-aware effective-turnover calculation."""
    with st.expander("有效换手率验证模式（可选）"):
        st.write(
            "免费公开日线只能稳定取得普通换手率。若你有同一日期、"
            "同一单位的无限售流通股本和自由流通股本，可以在这里验证"
            "有效换手率；系统不会自动猜测缺失股本。"
        )
        with st.form("effective_turnover_verification"):
            share_columns = st.columns(2)
            circulating_shares = share_columns[0].number_input(
                "无限售流通股本",
                min_value=0.0,
                value=0.0,
                step=1_000.0,
                help="可使用万股、亿股或股，但两个输入必须采用同一单位。",
            )
            free_float_shares = share_columns[1].number_input(
                "自由流通股本",
                min_value=0.0,
                value=0.0,
                step=1_000.0,
                help="应排除大股东、战略持股等实际上不易交易的股份。",
            )
            evidence_columns = st.columns(2)
            evidence_date = evidence_columns[0].date_input(
                "股本数据日期",
                value=date.fromisoformat(snapshot["latest_date"]),
                max_value=date.today(),
            )
            evidence_source = evidence_columns[1].text_input(
                "可追溯来源",
                placeholder="例如：公司公告第X页或已授权数据接口",
            )
            submitted = st.form_submit_button(
                "验证有效换手率",
                width="stretch",
            )

        if not submitted:
            st.caption(
                "计算公式：普通换手率 × 无限售流通股本 ÷ "
                "自由流通股本。两个股本输入只要求单位一致。"
            )
            return
        if snapshot["ordinary_turnover"] is None:
            st.error("当前缺少普通换手率，无法继续验证有效换手率。")
            return
        if not evidence_source.strip():
            st.error("请填写股本数据的可追溯来源。")
            return
        if evidence_date.isoformat() > snapshot["latest_date"]:
            st.error("股本数据日期不能晚于当前行情日期。")
            return

        try:
            result = calculate_effective_turnover(
                snapshot["ordinary_turnover"],
                circulating_shares,
                free_float_shares,
            )
        except ValueError as error:
            st.error(str(error))
            return

        result_columns = st.columns(3)
        result_columns[0].metric(
            "自由流通股本占比",
            _format_percent(result["free_float_ratio"]),
        )
        result_columns[1].metric(
            "换手率调整倍数",
            f"{result['adjustment_multiple']:.2f}倍",
        )
        result_columns[2].metric(
            "验证后的有效换手率",
            _format_percent(result["effective_turnover"]),
        )
        st.success(
            f"计算完成：{result['formula']}。"
        )
        st.caption(
            f"行情日期：{snapshot['latest_date']}；股本日期："
            f"{evidence_date.isoformat()}；来源：{evidence_source.strip()}。"
            "若两个日期不同，仍应检查期间是否发生增发、回购、解禁或"
            "其他股本变化。"
        )


def render_volume_turnover_page() -> None:
    """Render a dedicated, non-predictive participation research page."""
    apply_product_theme()
    show_compact_page_header(
        "03 / 成交量与换手率 · PARTICIPATION RESEARCH",
        "成交量与换手率研究",
        "分开核验成交量、普通换手率和可选有效换手率，"
        "观察交易活跃度而不预测未来涨跌。",
    )
    company = _selected_company()
    if company is None:
        st.warning("请先在首页选择一家中国上市公司。")
        _render_company_search(
            key_prefix="volume_turnover",
            navigate_on_success=False,
        )
        show_product_footer()
        return

    _show_company_banner(company)
    end_date = date.today()
    start_date = end_date - timedelta(days=550)
    started_at = perf_counter()
    try:
        with st.status(
            "正在读取成交量与换手率历史……",
            expanded=True,
        ) as run_status:
            market_frame = load_a_share_history(
                company["code"],
                start_date.isoformat(),
                end_date.isoformat(),
                "qfq",
            )
            _write_run_status(
                run_status,
                f"已取得 {len(market_frame)} 个交易日，正在计算历史基准。"
            )
            snapshot = build_volume_turnover_snapshot(
                market_frame,
                company,
            )
            history = build_volume_turnover_history(market_frame)
            elapsed_seconds = perf_counter() - started_at
            _update_run_status(
                run_status,
                label=(
                    "成交量与换手率核验完成｜"
                    f"{elapsed_seconds:.1f} 秒"
                ),
                state="complete",
                expanded=False,
            )
    except (DataSourceError, ValueError) as error:
        _update_run_status(
            run_status,
            label="成交量与换手率数据链暂不可用",
            state="error",
            expanded=False,
        )
        st.error(str(error))
        st.info(
            "公开行情恢复后可直接重试；系统不会用估算值替代缺失数据。"
        )
        show_product_footer()
        return

    _show_research_run_summary(
        elapsed_seconds,
        {
            "公开行情": True,
            "普通换手率": snapshot["ordinary_turnover"] is not None,
        },
    )

    metric_columns = st.columns(4)
    metric_columns[0].metric(
        "最新成交量倍数",
        (
            "数据不足"
            if snapshot["volume_ratio_20d"] is None
            else f"{snapshot['volume_ratio_20d']:.2f}倍"
        ),
        snapshot["price_volume_pattern"],
        delta_color="off",
    )
    metric_columns[1].metric(
        "成交量历史分位",
        _format_percent(snapshot["volume_percentile_250d"]),
        (
            f"此前{snapshot['volume_percentile_sessions']}个有效交易日"
        ),
        delta_color="off",
    )
    metric_columns[2].metric(
        "普通换手率",
        _format_percent(snapshot["ordinary_turnover"]),
    )
    metric_columns[3].metric(
        "普通换手率历史分位",
        _format_percent(snapshot["turnover_percentile_250d"]),
        (
            f"此前{snapshot['turnover_percentile_sessions']}个有效交易日"
        ),
        delta_color="off",
    )
    st.caption(
        f"数据截至 {snapshot['latest_date']}；来源：{snapshot['source']}。"
        f"{snapshot['turnover_status']}。"
    )

    st.subheader("近20日活跃度结构")
    activity_columns = st.columns(3)
    activity_columns[0].metric(
        "明显放量日",
        f"{snapshot['high_volume_days']}日",
        "成交量≥前20日中位数2倍",
        delta_color="off",
    )
    activity_columns[1].metric(
        "普通换手率高位日",
        f"{snapshot['high_turnover_days']}日",
        "达到此前历史90%分位",
        delta_color="off",
    )
    activity_columns[2].metric(
        "两项同时出现",
        f"{snapshot['compound_activity_days']}日",
        "只描述重合，不代表强弱评分",
        delta_color="off",
    )

    with st.container(border=True):
        st.markdown("**规则化观察**")
        for observation in snapshot["observations"]:
            st.write(f"- {observation}")

    figure = _build_volume_turnover_figure(history, company)
    st.plotly_chart(
        figure,
        width="stretch",
        config={"displaylogo": False},
    )
    st.caption(
        "柱形表示当日成交量相对此前20日中位数的倍数；"
        "折线表示普通换手率。所有滚动基准都排除当日和未来数据。"
    )

    if snapshot["events"]:
        st.subheader("近20日异常活跃记录")
        event_rows = [
            {
                "日期": event["date"],
                "触发项目": event["event_type"],
                "日涨跌幅": _format_percent(event["daily_return"]),
                "成交量倍数": (
                    "数据不足"
                    if event["volume_ratio_20d"] is None
                    else f"{event['volume_ratio_20d']:.2f}倍"
                ),
                "普通换手率": _format_percent(event["turnover"]),
                "换手率历史分位": _format_percent(
                    event["turnover_percentile_250d"]
                ),
            }
            for event in snapshot["events"]
        ]
        st.dataframe(
            pd.DataFrame(event_rows),
            hide_index=True,
            width="stretch",
        )
    else:
        st.info(
            "近20个交易日未触发“明显放量”或“普通换手率历史高位”规则。"
        )

    _show_effective_turnover_verification(snapshot)
    st.warning(
        "成交量、普通换手率和有效换手率只描述交易参与程度。"
        "高活跃度可能对应上涨、下跌或事件冲击，不构成买入、"
        "卖出或持有建议。"
    )
    show_product_footer()


def render_limit_up_board_page() -> None:
    """Render one recent public limit-up pool as a research-first wall."""
    apply_product_theme()
    show_compact_page_header(
        "04 / 每日涨停板观察台 · LIMIT-UP BOARD",
        "每日涨停板观察台",
        "按交易日查看涨停家数、连板、成交额、普通换手率、"
        "封板时间和行业集中度，再选择需要深入研究的公司。",
    )
    st.info(
        "这是按需读取的公开涨停股池，不需要开发者每天手工更新。"
        "页面只描述已经发生的交易事实，不预测次日表现。"
    )

    with st.form("limit_up_board_form"):
        selected_date = st.date_input(
            "选择近期交易日",
            value=date.today(),
            max_value=date.today(),
            help=(
                "公开接口只提供近期数据；周末、休市日或数据尚未更新时，"
                "可选择前一个交易日。"
            ),
        )
        submitted = st.form_submit_button(
            "读取该日涨停板",
            type="primary",
            width="stretch",
        )

    if submitted:
        if not isinstance(selected_date, date):
            st.session_state.pop("limit_up_board_snapshot", None)
            st.error("请选择一个有效日期。")
        else:
            try:
                with st.spinner("正在读取并校验公开涨停股池……"):
                    pool_frame = load_limit_up_pool(
                        selected_date.isoformat()
                    )
                    snapshot = build_limit_up_board_snapshot(
                        pool_frame,
                        selected_date,
                    )
                st.session_state["limit_up_board_snapshot"] = snapshot
            except (DataSourceError, ValueError) as error:
                st.session_state.pop("limit_up_board_snapshot", None)
                st.error(str(error))

    stored_snapshot = st.session_state.get("limit_up_board_snapshot")
    snapshot: LimitUpBoardSnapshot | None = (
        stored_snapshot if isinstance(stored_snapshot, dict) else None
    )
    if snapshot is None:
        st.caption(
            "选择日期并点击读取后，这里会生成当日涨停板信息墙。"
        )
        show_product_footer()
        return

    rows = snapshot["rows"]
    if not rows:
        st.warning(
            f"{snapshot['trade_date']} 未取得涨停股池。"
            "该日可能休市、没有涨停公司，或公开源尚未更新；"
            "请尝试前一个交易日。"
        )
        show_product_footer()
        return

    summary_columns = st.columns(4)
    summary_columns[0].metric(
        "涨停家数",
        f"{snapshot['total_count']} 家",
    )
    summary_columns[1].metric(
        "连板家数",
        f"{snapshot['consecutive_board_count']} 家",
    )
    max_boards = snapshot["max_consecutive_boards"]
    summary_columns[2].metric(
        "最高连板",
        "数据不足" if max_boards is None else f"{max_boards} 板",
    )
    summary_columns[3].metric(
        "普通换手率中位数",
        _format_percent(snapshot["median_turnover"]),
    )
    st.caption(
        f"交易日：{snapshot['trade_date']}｜"
        f"首板 {snapshot['first_board_count']} 家｜"
        f"行业数量最多：{snapshot['leading_industry']}"
        f"（{snapshot['leading_industry_count']} 家）｜"
        f"来源：{snapshot['source']}。"
    )

    review = snapshot["review"]
    st.subheader("盘后市场结构复盘")
    st.caption(
        "以下内容由 Python 按固定规则汇总，只描述当日涨停池的"
        "梯队、行业、封板节奏和回封记录，不生成涨跌预测。"
    )
    review_metrics = st.columns(4)
    valid_first_times = review["valid_first_limit_time_count"]
    review_metrics[0].metric(
        "10点前首次封板",
        (
            "数据不足"
            if valid_first_times == 0
            else f"{review['early_seal_count']}/{valid_first_times} 家"
        ),
    )
    valid_break_counts = review["valid_break_count_count"]
    review_metrics[1].metric(
        "开板后回封",
        (
            "数据不足"
            if valid_break_counts == 0
            else f"{review['resealed_count']}/{valid_break_counts} 家"
        ),
    )
    review_metrics[2].metric(
        "头部行业占比",
        _format_percent(review["leading_industry_share"]),
    )
    review_metrics[3].metric(
        "涨停梯队层数",
        f"{len(review['ladder'])} 层",
    )

    structure_columns = st.columns([1, 2])
    with structure_columns[0]:
        st.markdown("#### 涨停梯队")
        ladder_rows = [
            {
                "梯队": f"{row['boards']}板",
                "公司数": row["company_count"],
                "占当日涨停": _format_percent(row["share"]),
            }
            for row in review["ladder"]
        ]
        st.dataframe(
            pd.DataFrame(ladder_rows),
            hide_index=True,
            width="stretch",
        )

    with structure_columns[1]:
        st.markdown("#### 行业结构（前五）")
        industry_rows = [
            {
                "行业": row["industry"],
                "涨停家数": row["company_count"],
                "连板家数": row["consecutive_count"],
                "合计成交额": _format_optional_cny_100m(
                    row["total_amount"]
                ),
                "普通换手率中位数": _format_percent(
                    row["median_turnover"]
                ),
            }
            for row in review["industries"][:5]
        ]
        st.dataframe(
            pd.DataFrame(industry_rows),
            hide_index=True,
            width="stretch",
        )

    with st.container(border=True):
        st.markdown("**规则化观察**")
        for observation in review["observations"]:
            st.write(f"- {observation}")

    st.subheader("头部涨停观察")
    st.caption(
        "默认依次按连板数、炸板次数、首次封板时间、封板资金和"
        "普通换手率排序；这是研究顺序，不是买入评分。"
    )
    for rank, row in enumerate(rows[:5], start=1):
        company = build_company_identity(row["code"], row["name"])
        with st.container(border=True):
            title_column, status_column = st.columns([3, 1])
            title_column.markdown(
                f"### {rank}. {row['name']}｜"
                f"{company['canonical_code']}"
            )
            boards = row["consecutive_boards"]
            status_column.markdown(
                "**连板数据不足**"
                if boards is None
                else f"**{boards} 板**"
            )

            metric_columns = st.columns(4)
            metric_columns[0].metric(
                "涨跌幅",
                _format_percent(row["daily_change"]),
            )
            metric_columns[1].metric(
                "普通换手率",
                _format_percent(row["turnover"]),
            )
            metric_columns[2].metric(
                "成交额",
                _format_optional_cny_100m(row["amount"]),
            )
            metric_columns[3].metric(
                "首次封板",
                row["first_limit_time"] or "数据不足",
            )
            break_count = row["break_count"]
            st.caption(
                f"行业：{row['industry']}｜"
                f"炸板次数："
                f"{'数据不足' if break_count is None else break_count}｜"
                f"封板资金：{_format_optional_cny_100m(row['sealed_funds'])}｜"
                f"涨停统计：{row['limit_statistics'] or '数据不足'}。"
            )
            if st.button(
                "进入该公司研究中心",
                width="stretch",
                key=(
                    f"limit_up_to_company_{snapshot['trade_date']}_"
                    f"{row['code']}"
                ),
            ):
                _store_selected_company(company)
                _switch_page("company")

    st.subheader("完整观察表")
    table_rows = []
    for rank, row in enumerate(rows[:30], start=1):
        table_rows.append(
            {
                "排名": rank,
                "代码": row["code"],
                "名称": row["name"],
                "连板数": row["consecutive_boards"],
                "普通换手率": _format_percent(row["turnover"]),
                "成交额": _format_optional_cny_100m(row["amount"]),
                "封板资金": _format_optional_cny_100m(
                    row["sealed_funds"]
                ),
                "首次封板": row["first_limit_time"] or "数据不足",
                "炸板次数": row["break_count"],
                "所属行业": row["industry"],
            }
        )
    st.dataframe(
        pd.DataFrame(table_rows),
        hide_index=True,
        width="stretch",
    )
    if snapshot["total_count"] > len(table_rows):
        st.caption(
            f"为保持页面清晰，表格展示排序后的前 {len(table_rows)} 家；"
            f"当日涨停股池共 {snapshot['total_count']} 家。"
        )

    action_columns = st.columns(2)
    action_columns[0].link_button(
        "查看东方财富涨停板原始页面",
        "https://quote.eastmoney.com/ztb/detail#type=ztgc",
        width="stretch",
    )
    if action_columns[1].button(
        "用股票代码进入自选股雷达",
        width="stretch",
        key=f"limit_up_to_radar_{snapshot['trade_date']}",
    ):
        _switch_page("radar")

    with st.expander("为什么这里仍标注普通换手率"):
        st.write(
            "公开涨停股池提供的是成交量相对于普通流通股本的换手率。"
            "真正的有效换手率还需要可核验的时点自由流通股本，"
            "目前可靠接口需要额外数据权限，因此本产品不会自行估算或"
            "把普通换手率改名为有效换手率。"
        )
    st.warning(
        "涨停、连板、高成交额或高换手都不等于公司基本面改善，"
        "也不构成买入、卖出或持有建议。首次与最后封板时间、"
        "炸板次数和封板资金均为公开源的当日快照。"
    )
    show_product_footer()


def _scan_market_radar_company(
    company: CompanyIdentity,
    start_date: date,
    end_date: date,
) -> ResearchQueueRow:
    """Build one isolated company result for the bounded radar worker pool."""
    market_frame = load_a_share_history(
        company["code"],
        start_date.isoformat(),
        end_date.isoformat(),
        "qfq",
    )
    activity = calculate_market_activity(market_frame, company)
    radar_row = build_market_radar_row(
        company,
        activity,
        market_source=str(
            market_frame.attrs.get(
                "source",
                "公开行情适配器",
            )
        ),
        turnover_source=str(
            market_frame.attrs.get(
                "turnover_source",
                "公开行情字段或暂未取得",
            )
        ),
    )
    disclosure_start = end_date - timedelta(days=45)
    try:
        announcements = load_company_announcements(
            company["code"],
            disclosure_start.isoformat(),
            end_date.isoformat(),
        )
    except (DataSourceError, ValueError):
        disclosure_records = None
        disclosure_status = "官方公告源暂不可用"
    else:
        disclosure_records = announcements.to_dict("records")
        disclosure_status = (
            f"已核验近45日公告 {len(disclosure_records)} 条"
        )
    return build_research_queue_row(
        radar_row,
        disclosure_records,
        as_of_date=end_date,
        disclosure_status=disclosure_status,
    )


def _scan_market_radar(
    codes: list[str],
) -> tuple[list[ResearchQueueRow], list[str]]:
    """Scan up to three companies concurrently and isolate every failure."""
    offline_matches = {
        code: matches[0]
        for code in codes
        if (matches := resolve_company(code, None))
        and matches[0]["name"] != "待核验公司"
    }
    unresolved_codes = [code for code in codes if code not in offline_matches]
    directory: pd.DataFrame | None = None
    if unresolved_codes:
        try:
            directory = load_a_share_directory()
        except (DataSourceError, ValueError):
            directory = None

    end_date = date.today()
    start_date = end_date - timedelta(days=430)
    companies: list[CompanyIdentity] = []
    failures: list[str] = []
    for code in codes:
        matches = (
            [offline_matches[code]]
            if code in offline_matches
            else resolve_company(code, directory)
        )
        if not matches:
            failures.append(f"{code}：无法识别为当前支持的A股代码。")
            continue
        companies.append(matches[0])

    if not companies:
        return [], failures

    # Three workers shorten a five-company scan without creating an
    # unbounded burst against the free server or the public data providers.
    with ThreadPoolExecutor(
        max_workers=min(3, len(companies)),
        thread_name_prefix="wfz-radar",
    ) as executor:
        company_futures = [
            (
                company,
                executor.submit(
                    _scan_market_radar_company,
                    company,
                    start_date,
                    end_date,
                ),
            )
            for company in companies
        ]

        rows: list[ResearchQueueRow] = []
        for company, future in company_futures:
            try:
                rows.append(future.result())
            except (DataSourceError, ValueError) as error:
                failures.append(f"{company['canonical_code']}：{error}")

    return rank_research_queue(rows), failures


def render_market_radar_page() -> None:
    """Render an on-demand, bounded watchlist research task queue."""
    apply_product_theme()
    show_compact_page_header(
        "05 / 自选股研究任务队列 · RESEARCH QUEUE",
        "自选股研究任务队列",
        "一次比较最多5家A股的涨停候选、成交量放大和普通换手率"
        "历史位置，再连接最近官方公告，生成可追溯的研究先后顺序。",
    )
    st.info(
        "这是按需扫描，不会提前下载或永久保存全市场资料。"
        "P1/P2/P3只安排研究任务先后，不代表上涨概率或投资价值。"
    )

    browser_snapshot = _browser_research_snapshot()
    local_watchlist = browser_snapshot.get("watchlist", [])
    local_watchlist_codes = [
        item["code"]
        for item in local_watchlist
        if isinstance(item, Mapping)
        and isinstance(item.get("code"), str)
    ][:MAX_LOCAL_WATCHLIST]
    default_watchlist_text = (
        ", ".join(local_watchlist_codes)
        if local_watchlist_codes
        else "600519, 300750, 000001"
    )
    if local_watchlist_codes:
        st.caption(
            f"已从当前浏览器读取 {len(local_watchlist_codes)} 家本机自选股；"
            "可一键扫描，也可在下方临时修改代码。"
        )

    with st.form("market_radar_form"):
        watchlist_text = st.text_area(
            "输入最多5个六位股票代码",
            value=default_watchlist_text,
            height=90,
            placeholder="例如：600519, 300750, 000001",
            help="可使用逗号、空格、分号或顿号分隔。",
        )
        local_submitted = False
        if local_watchlist_codes:
            local_submitted = st.form_submit_button(
                f"一键扫描我的本机自选股（{len(local_watchlist_codes)}家）",
                type="primary",
                width="stretch",
            )
        manual_submitted = st.form_submit_button(
            "开始扫描自选股",
            type="secondary" if local_watchlist_codes else "primary",
            width="stretch",
        )

    submitted = local_submitted or manual_submitted
    if submitted:
        scan_text = (
            ", ".join(local_watchlist_codes)
            if local_submitted
            else watchlist_text
        )
        parsed = parse_watchlist_codes(scan_text)
        if parsed["invalid_tokens"]:
            st.warning(
                "以下内容不是六位股票代码，已跳过："
                + "、".join(parsed["invalid_tokens"])
            )
        if parsed["duplicate_count"]:
            st.caption(
                f"已自动去除 {parsed['duplicate_count']} 个重复代码。"
            )
        if parsed["omitted_count"]:
            st.warning(
                f"为保护免费服务器，本次只扫描前5家公司；"
                f"另有 {parsed['omitted_count']} 家未进入本次扫描。"
            )

        if parsed["codes"]:
            scan_started = perf_counter()
            with st.spinner(
                f"正在核验 {len(parsed['codes'])} 家公司的公开行情……"
            ):
                rows, failures = _scan_market_radar(parsed["codes"])
            st.session_state["market_radar_rows"] = rows
            st.session_state["market_radar_failures"] = failures
            st.session_state["market_radar_elapsed_seconds"] = (
                perf_counter() - scan_started
            )
        else:
            st.session_state["market_radar_rows"] = []
            st.session_state["market_radar_failures"] = []
            st.session_state.pop("market_radar_elapsed_seconds", None)
            st.error("请至少输入一个有效的六位股票代码。")

    rows = st.session_state.get("market_radar_rows", [])
    failures = st.session_state.get("market_radar_failures", [])
    if not isinstance(rows, list):
        rows = []
    if not isinstance(failures, list):
        failures = []
    elapsed_seconds = st.session_state.get(
        "market_radar_elapsed_seconds"
    )
    if isinstance(elapsed_seconds, (int, float)):
        st.caption(
            f"本次扫描用时 {elapsed_seconds:.1f} 秒；"
            "为兼顾速度与公开数据源稳定性，同时核验最多3家公司。"
        )

    if failures:
        with st.expander("查看未完成扫描的公司", expanded=False):
            for failure in failures:
                st.write(f"- {failure}")

    if not rows:
        st.caption(
            "输入代码并点击扫描后，这里会生成当日自选股研究任务队列。"
        )
        show_product_footer()
        return

    p1_count = sum(
        row["research_priority"] == "P1｜立即核查" for row in rows
    )
    triggered_company_count = sum(
        row["trigger_count"] > 0 for row in rows
    )
    latest_dates = sorted({row["latest_date"] for row in rows})
    disclosure_verified_count = sum(
        row["disclosure_status"].startswith("已核验") for row in rows
    )
    summary_columns = st.columns(4)
    summary_columns[0].metric("成功扫描", f"{len(rows)} 家")
    summary_columns[1].metric(
        "P1研究任务",
        f"{p1_count} 家",
    )
    summary_columns[2].metric(
        "行情至少触发一项",
        f"{triggered_company_count} 家",
    )
    summary_columns[3].metric(
        "公告完成核验",
        f"{disclosure_verified_count} 家",
    )
    st.caption(
        "行情日期："
        + "、".join(latest_dates)
        + "。P1优先处理复合行情异动或两天内高关注官方公告；"
        "P2处理单项异动或七天内高/中关注公告；其余为P3。"
        "公告关注度来自标题主题，不表示利好或利空。"
    )
    queue_report_date = date.today()
    queue_report_html = build_research_queue_report_html(
        rows,
        scan_date=queue_report_date,
        failures=failures,
    )
    st.markdown("#### 保存本次任务队列")
    st.caption(
        "下载文件可离线打开，保留每家公司的优先级、"
        "任务原因、数据来源和官方公告链接。"
    )
    st.download_button(
        "下载自选股研究任务简报（HTML）",
        data=queue_report_html.encode("utf-8"),
        file_name=(
            f"WFZ_{queue_report_date.isoformat()}_自选股研究任务简报.html"
        ),
        mime="text/html",
        width="stretch",
        key="market_radar_queue_report",
    )

    for rank, row in enumerate(rows, start=1):
        company = row["company"]
        with st.container(border=True):
            title_column, status_column = st.columns([3, 1])
            title_column.markdown(
                f"### {rank}. {company['name']}｜"
                f"{company['canonical_code']}"
            )
            status_column.markdown(f"**{row['research_priority']}**")
            status_column.caption(row["radar_status"])

            metric_columns = st.columns(4)
            metric_columns[0].metric(
                "最新日涨跌幅",
                _format_percent(row["daily_return"]),
            )
            volume_ratio = row["volume_ratio_20d"]
            metric_columns[1].metric(
                "成交量 / 前20日",
                (
                    "数据不足"
                    if volume_ratio is None
                    else f"{volume_ratio:.2f}倍"
                ),
            )
            metric_columns[2].metric(
                "普通换手率",
                _format_percent(row["turnover"]),
            )
            metric_columns[3].metric(
                "换手率历史分位",
                _format_percent(row["turnover_percentile_250d"]),
            )

            signal_text = (
                "、".join(row["triggered_signals"])
                if row["triggered_signals"]
                else "未触发三项门槛"
            )
            st.write(
                f"**触发证据：{signal_text}**｜"
                f"可用证据 {row['available_signal_count']}/3 项。"
            )
            st.markdown(
                "**研究任务原因：** "
                + "；".join(row["research_reasons"])
                + "。"
            )
            st.caption(
                f"行情来源：{row['market_source']}｜"
                f"换手率来源：{row['turnover_source']}。"
                "普通换手率不等同于有效换手率。"
            )
            latest_disclosure = row["latest_disclosure"]
            if latest_disclosure is None:
                st.caption(
                    f"官方公告：{row['disclosure_status']}。"
                    "系统不会用媒体摘要或AI猜测填补。"
                )
            else:
                st.markdown("##### 最近官方公告")
                disclosure_text, disclosure_link = st.columns([5, 1])
                with disclosure_text:
                    st.write(f"**{latest_disclosure['title']}**")
                    st.caption(
                        f"{latest_disclosure['published_date']}｜"
                        f"{latest_disclosure['category']}｜"
                        f"关注程度：{latest_disclosure['attention']}｜"
                        f"距扫描日 {latest_disclosure['days_old']} 天｜"
                        "来源：官方披露"
                    )
                with disclosure_link:
                    st.link_button(
                        "查看原文 ↗",
                        latest_disclosure["source_url"],
                        width="stretch",
                    )

            action_columns = st.columns([2, 1, 1])
            if action_columns[0].button(
                "生成完整研究简报",
                type="primary",
                width="stretch",
                key=f"radar_to_comprehensive_{company['canonical_code']}",
            ):
                _handoff_market_radar_to_comprehensive(row)
            if action_columns[1].button(
                "异动复盘",
                width="stretch",
                key=f"radar_to_anomaly_{company['canonical_code']}",
            ):
                _store_selected_company(company)
                _switch_page("anomaly")
            if action_columns[2].button(
                "公司资料",
                width="stretch",
                key=f"radar_to_company_{company['canonical_code']}",
            ):
                _store_selected_company(company)
                _switch_page("company")

    st.warning(
        "任务队列只整理已经发生的公开行情和官方公告。涨停候选仍需"
        "核验交易所例外规则，公告与异动时间接近也不能证明因果关系；"
        "P1/P2/P3均不等于利好、利空或买卖信号。"
    )
    show_product_footer()


def render_market_anomaly_page() -> None:
    """Render a deterministic anomaly-to-official-evidence workflow."""
    apply_product_theme()
    show_compact_page_header(
        "06 / 市场异动研究 · MARKET ANOMALY AGENT",
        "市场异动研究 Agent",
        "自动核验涨停候选、成交量和普通换手率的历史位置，"
        "再把候选日期连接到当时已经公开的官方公告。",
    )
    company = _selected_company()
    if company is None:
        st.warning("请先在首页选择一家中国上市公司。")
        _render_company_search(
            key_prefix="anomaly",
            navigate_on_success=False,
        )
        show_product_footer()
        return

    _show_company_banner(company)
    st.markdown(
        "**行情核验 → Python规则筛选 → 异动分型 → "
        "公告时间隔离 → Historical Lens复盘**"
    )
    st.caption(
        "筛选和关键数字全部由确定性Python完成；"
        "Agent负责组织步骤和证据，不负责预测价格。"
    )

    end_date = date.today()
    start_date = end_date - timedelta(days=550)
    started_at = perf_counter()
    try:
        with st.status(
            "正在同时读取行情与官方公告……",
            expanded=True,
        ) as run_status:
            (
                market_frame,
                announcements,
                market_error,
                announcement_error,
            ) = load_company_research_sources(
                company["code"],
                start_date.isoformat(),
                end_date.isoformat(),
                "qfq",
            )
            if market_frame is None:
                raise DataSourceError(
                    market_error or "公开行情源本次未返回有效数据。"
                )
            _write_run_status(
                run_status,
                f"已取得 {len(market_frame)} 个交易日，正在执行异动规则。"
            )
            activity = calculate_market_activity(market_frame, company)
            history_events = scan_market_activity_events(
                market_frame,
                company,
                max_results=60,
            )
            events = history_events[:8]
            report = build_market_anomaly_report(activity, events)
            if announcements is not None:
                _write_run_status(
                    run_status,
                    f"官方公告已完成核验，共 {len(announcements)} 条。"
                )
            else:
                _write_run_status(
                    run_status,
                    "官方公告源本次未完成；行情异动结果仍可独立查看。"
                )
            elapsed_seconds = perf_counter() - started_at
            _update_run_status(
                run_status,
                label=(
                    f"市场异动扫描完成｜发现 {len(events)} 个候选｜"
                    f"{elapsed_seconds:.1f} 秒"
                ),
                state="complete",
                expanded=False,
            )
    except (DataSourceError, ValueError) as error:
        _update_run_status(
            run_status,
            label="市场异动行情数据链暂不可用",
            state="error",
            expanded=False,
        )
        st.error(str(error))
        st.info(
            "公开行情源恢复后可直接重试；"
            "系统不会用过期样例或AI猜测替代真实行情。"
        )
        show_product_footer()
        return

    _show_research_run_summary(
        elapsed_seconds,
        {
            "公开行情": True,
            "普通换手率": activity["turnover"] is not None,
            "官方公告": announcements is not None and not announcement_error,
        },
    )

    _show_market_anomaly_report(report)
    st.divider()
    _show_market_activity_evidence(activity)
    st.divider()
    _show_anomaly_event_research(
        events,
        company,
        announcements,
        history_events=history_events,
        market_source=str(
            market_frame.attrs.get("source", "公开行情适配器")
        ),
        turnover_source=str(
            market_frame.attrs.get(
                "turnover_source",
                "公开行情字段或暂未取得",
            )
        ),
    )

    st.caption(
        f"行情来源：{market_frame.attrs.get('source', '公开行情适配器')}｜"
        "前复权日线仅用于连续趋势与异动筛选；"
        "完整历史复盘会切换为不复权口径并重新计算。"
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


def _show_event_evidence_chain(
    chain: EventEvidenceChain,
    *,
    event_context: str | None = None,
) -> None:
    """Show official disclosures near a selected date without causal claims."""
    chain_title = (
        "异动—公告证据链"
        if event_context
        else "所选日期—公告证据链"
    )
    st.markdown(f"#### {chain_title}")
    context_text = f"｜异动类型：{event_context}" if event_context else ""
    st.caption(
        f"研究日期：{chain['event_date']}{context_text}｜"
        f"只检查含当日在内的最近 {chain['window_days']} 个自然日，"
        "且只允许使用当时已经公开的官方信息。"
    )

    if chain["status"] == "none":
        st.info(chain["conclusion"])
    else:
        st.success(chain["conclusion"])
        for item in chain["matches"]:
            with st.container(border=True):
                text_column, link_column = st.columns([5, 1])
                with text_column:
                    st.markdown(f"**{item['title']}**")
                    st.caption(
                        f"{item['relation']}｜{item['published_date']}｜"
                        f"{item['source_type']}｜证据等级 "
                        f"{item['evidence_grade']}"
                    )
                with link_column:
                    st.link_button(
                        "查看原文 ↗",
                        item["source_url"],
                        width="stretch",
                    )
        if chain["matched_count"] > len(chain["matches"]):
            st.caption(
                f"当前窗口共匹配 {chain['matched_count']} 条，"
                f"按时间接近程度展示前 {len(chain['matches'])} 条。"
            )

    st.warning(chain["limitation"])
    st.caption(
        f"时间隔离审计：另有 {chain['future_excluded_count']} 条"
        "截止日后公告未进入本证据链。"
    )


def _format_cny_100m(value: float) -> str:
    """Display audited RMB amounts in a compact Chinese reporting unit."""
    return f"¥{value / 100_000_000:,.2f}亿"


def _company_identity_from_financial_case(
    case: FinancialHistoryCase,
) -> CompanyIdentity:
    """Build the shared company identity directly from an audited case."""
    return {
        "code": case["company_code"],
        "name": case["company_name"],
        "exchange": case["exchange"],
        "exchange_name": case["exchange_name"],
        "canonical_code": case["canonical_code"],
    }


def _show_verified_financial_history(
    company: CompanyIdentity,
    selected_date: date,
) -> None:
    """Show publication-date-filtered audited history where available."""
    st.divider()
    st.subheader("当时已公开的多年财务趋势")
    st.caption(
        "每个年度只采用历史截止日前已经发布的官方年报版本；"
        "若后来发生追溯调整，系统从调整公告日开始切换版本。"
    )

    try:
        verified_cases = load_financial_history_catalog()
    except ValueError as error:
        st.warning(str(error))
        return
    verified_codes = {case["company_code"] for case in verified_cases}
    if company["code"] not in verified_codes:
        covered_names = "、".join(
            case["company_name"] for case in verified_cases
        )
        st.info(
            f"多年财务页码基准目前覆盖{covered_names}。"
            "其他A股公司仍可使用行情、公告和年报原文分析。"
        )
        return

    try:
        result = select_financial_history_as_of(
            load_verified_financial_history(company["code"]),
            selected_date,
        )
    except ValueError as error:
        st.warning(str(error))
        return

    points = result["points"]
    if not points:
        st.info(
            "截至所选日期，旗舰基准中尚无已经公开的完整年度财务数据。"
        )
        return

    latest = points[-1]
    metric_columns = st.columns(4)
    metric_columns[0].metric(
        f"{latest['period_year']}年营业收入",
        _format_cny_100m(latest["revenue"]),
        _format_percent(latest["revenue_growth"]),
    )
    metric_columns[1].metric(
        "归母净利润",
        _format_cny_100m(latest["net_profit"]),
        _format_percent(latest["net_profit_growth"]),
    )
    metric_columns[2].metric(
        "经营现金流净额",
        _format_cny_100m(latest["operating_cash_flow"]),
        _format_percent(latest["operating_cash_flow_growth"]),
    )
    metric_columns[3].metric(
        "负债占总资产",
        _format_percent(latest["liabilities_to_assets"]),
        _format_percentage_point_change(
            latest["liabilities_to_assets_change"]
        ),
        delta_color="off",
        help="总负债 ÷ 总资产，由Python确定性计算。",
    )

    with st.expander("查看盈利质量与现金质量", expanded=True):
        quality_columns = st.columns(4)
        quality_columns[0].metric(
            "归母净利率",
            _format_percent(latest["net_margin"]),
            _format_percentage_point_change(latest["net_margin_change"]),
            delta_color="off",
            help="归母净利润 ÷ 营业收入，由Python确定性计算。",
        )
        quality_columns[1].metric(
            "经营现金 / 归母净利润",
            f"{latest['cash_conversion']:.2f}倍",
            _format_multiple_change(latest["cash_conversion_change"]),
            delta_color="off",
            help=(
                "经营活动现金流量净额 ÷ 归母净利润。"
                "它用于观察利润与经营现金的匹配程度，"
                "不能单独判断企业质量。"
            ),
        )
        quality_columns[2].metric(
            "总资产",
            _format_cny_100m(latest["total_assets"]),
        )
        quality_columns[3].metric(
            "总负债",
            _format_cny_100m(latest["total_liabilities"]),
        )
        st.caption(
            "净利率、现金利润比和负债占总资产均由已核验年报数据计算。"
            "现金利润比高于或低于1倍都需要结合营运资本、税费、"
            "季节性和一次性项目继续解释，页面不自动给出利好或利空判断。"
        )

    if len(points) >= 2:
        try:
            import plotly.graph_objects as go
        except ModuleNotFoundError:
            st.caption(
                "当前环境未加载交互式图表组件；"
                "下方核验数据和年报证据仍可正常使用。"
            )
        else:
            years = [str(point["period_year"]) for point in points]
            figure = go.Figure()
            series = (
                ("营业收入", "revenue"),
                ("归母净利润", "net_profit"),
                ("经营现金流净额", "operating_cash_flow"),
            )
            for label, field_name in series:
                values = [
                    point[field_name] / 100_000_000
                    for point in points
                ]
                figure.add_trace(
                    go.Scatter(
                        x=years,
                        y=values,
                        mode="lines+markers",
                        name=label,
                        hovertemplate=(
                            f"{label}：%{{y:,.2f}}亿元"
                            "<extra></extra>"
                        ),
                    )
                )
            figure.update_layout(
                height=390,
                margin={"l": 15, "r": 15, "t": 20, "b": 20},
                hovermode="x unified",
                xaxis_title="财务年度",
                yaxis_title="人民币亿元",
                legend={"orientation": "h", "y": 1.12},
            )
            st.plotly_chart(
                figure,
                width="stretch",
                config={"displaylogo": False},
            )
    else:
        st.info("当前截止日只有一个完整年度，尚不能形成跨年趋势。")

    latest_growths = (
        latest["revenue_growth"],
        latest["net_profit_growth"],
        latest["operating_cash_flow_growth"],
    )
    if all(value is not None for value in latest_growths):
        st.info(
            f"{latest['period_year']}年相较上一已核验年度："
            f"营业收入 {_format_percent(latest['revenue_growth'])}，"
            f"归母净利润 {_format_percent(latest['net_profit_growth'])}，"
            "经营现金流净额 "
            f"{_format_percent(latest['operating_cash_flow_growth'])}。"
            "这里只描述年报数字变化，不解释为股价信号。"
        )

    st.markdown("#### 年报页码与版本")
    for point in reversed(points):
        basis_text = {
            "original": "首次披露",
            "restated": "追溯调整后",
            "reported": "本期披露",
        }[point["accounting_basis"]]
        with st.container(border=True):
            text_column, link_column = st.columns([5, 1])
            with text_column:
                st.markdown(
                    f"**{point['period_year']}年度｜{basis_text}**"
                )
                st.caption(
                    f"{point['report_title']}｜公开日期 "
                    f"{point['published_date'].isoformat()}｜"
                    f"主要数据第 {point['summary_page']} 页｜"
                    f"合并负债第 {point['balance_sheet_page']} 页｜"
                    "证据等级 A"
                )
                if point["notes"]:
                    st.caption(point["notes"])
            with link_column:
                st.link_button(
                    "查看年报 ↗",
                    point["source_url"],
                    width="stretch",
                )

    st.caption(
        f"时间隔离审计：截止 {result['as_of_date']}，"
        f"纳入 {len(points)} 个财务年度；另有 "
        f"{result['future_vintage_count']} 个尚未公开的报告版本被排除。"
    )


def render_historical_lens_page() -> None:
    """Render a point-in-time research view without look-ahead information."""
    apply_product_theme()
    show_compact_page_header(
        "07 / 历史回看 · HISTORICAL LENS",
        "Historical Lens｜回到当时再研究",
        "冻结历史信息截止线，先查看当时已经公开的证据，"
        "再单独揭示后来1、3、6个月的市场表现。",
    )
    today = date.today()
    deep_link = parse_historical_deep_link(
        st.query_params,
        today=today,
    )
    deep_link_prefill = None
    deep_link_context = None
    if deep_link is not None:
        deep_link_token = (
            f"{deep_link['code']}|{deep_link['event_date'].isoformat()}|"
            f"{deep_link['source'] or 'direct'}"
        )
        if (
            st.session_state.get("_historical_deep_link_token")
            != deep_link_token
        ):
            resolved_companies = resolve_company(deep_link["code"])
            if resolved_companies:
                _store_selected_company(resolved_companies[0])
                deep_link_prefill = deep_link["event_date"].isoformat()
                deep_link_context = (
                    "来自下载版异动研究报告"
                    if deep_link["source"] == "anomaly-report"
                    else "来自分享链接"
                )
            st.session_state["_historical_deep_link_token"] = deep_link_token

    company = _selected_company()
    if company is None:
        # The verified offline identity keeps the flagship demonstration usable
        # when the live company directory is temporarily unavailable.
        company = resolve_company("600519")[0]
        _store_selected_company(company)
        st.info("尚未选择公司，已载入首个演示对象：贵州茅台。")

    _show_company_banner(company)
    historical_mission_active = (
        st.session_state.get("historical_game_mission_id")
        == HISTORICAL_MISSION_ID
        and company["code"] == HISTORICAL_GAME_MISSION["company_code"]
    )
    if historical_mission_active:
        mission = HISTORICAL_GAME_MISSION
        with st.container(border=True):
            st.caption("研究员任务局已连接 · OPEN INVESTIGATION")
            st.markdown(f"#### {mission['title']}")
            st.write(mission["question"])
            st.caption(
                "请比较相邻日期中“当时已经公开的官方证据”是否发生变化。"
                "目标是找到证据第一次可见的边界，而不是猜测股价涨跌。"
            )
    st.info(
        "时间隔离规则：只有发布日期不晚于所选日期的信息，"
        "才允许进入“当时已知”。后来行情在点击前不会显示。"
    )

    prefill_raw = deep_link_prefill
    prefill_context = deep_link_context
    if prefill_raw is None:
        prefill_raw = st.session_state.pop(
            "historical_prefill_date",
            None,
        )
        prefill_context = st.session_state.pop(
            "historical_prefill_context",
            None,
        )
    prefill_date = None
    if prefill_raw is not None:
        try:
            candidate_date = date.fromisoformat(str(prefill_raw))
        except ValueError:
            candidate_date = None
        if (
            candidate_date is not None
            and today - timedelta(days=365 * 5)
            <= candidate_date
            <= today
        ):
            prefill_date = candidate_date

    earliest_date = today - timedelta(days=365 * 5)
    default_date = prefill_date or today - timedelta(days=365)
    selected_event = None
    flagship_events = []
    if company["code"] == "600519":
        try:
            flagship_events = load_moutai_flagship_events()
        except ValueError:
            flagship_events = []
            st.warning("已核验的重要日期暂时无法读取，可继续自由选择日期。")

        if flagship_events and not historical_mission_active:
            event_options = {"自由选择日期": None}
            for event in flagship_events:
                label = (
                    f"{event['event_date'].isoformat()}｜"
                    f"{event['title']}"
                )
                event_options[label] = event
            event_select_key = (
                f"historical_flagship_event_{company['code']}"
            )
            if prefill_date is not None:
                st.session_state.pop(event_select_key, None)
            event_label = st.selectbox(
                "快速选择已核验的重要日期",
                options=list(event_options),
                index=(
                    0
                    if prefill_date is not None
                    else len(event_options) - 1
                ),
                key=event_select_key,
                help=(
                    "这些日期只提供官方事件入口和时间锚点，"
                    "不会预设事件对股价的影响。"
                ),
            )
            selected_event = event_options[event_label]
            if selected_event is not None:
                default_date = selected_event["event_date"]

    if prefill_date is not None:
        context_text = (
            f"（{prefill_context}）"
            if isinstance(prefill_context, str)
            else ""
        )
        st.success(
            f"已从异常交易日回看 Agent 带入 {prefill_date.isoformat()}"
            f"{context_text}；以下内容仍严格按该日的信息截止线过滤。"
        )

    date_key_suffix = (
        selected_event["event_id"]
        if selected_event is not None
        else "custom"
    )
    date_input_key = (
        f"historical_timeline_{company['code']}_{date_key_suffix}"
    )
    if prefill_date is not None:
        st.session_state.pop(date_input_key, None)
    timeline_min = earliest_date
    timeline_max = today
    if historical_mission_active:
        timeline_min = max(
            earliest_date,
            HISTORICAL_GAME_MISSION["window_start"],
        )
        timeline_max = min(
            today,
            HISTORICAL_GAME_MISSION["window_end"],
        )
        if not timeline_min <= default_date <= timeline_max:
            default_date = HISTORICAL_GAME_MISSION["initial_date"]

    st.markdown("#### Historical Lens 时点滑轨")
    st.caption(
        "像调节滑动变阻器一样移动截止日，再锁定时点生成快照。"
        "控件放在表单中，拖动过程不会每天重复请求公开数据。"
    )
    with st.form(
        key=f"{date_input_key}_form",
        border=True,
    ):
        selected_date = st.slider(
            "拖动历史研究截止日",
            value=default_date,
            min_value=timeline_min,
            max_value=timeline_max,
            step=timedelta(days=1),
            format="YYYY-MM-DD",
            key=date_input_key,
            help=(
                "若所选日期不是交易日，系统会使用该日期之前最近一个"
                "交易日；证据仍按真实公开日期过滤。"
            ),
        )
        st.form_submit_button(
            "锁定这个时点并生成研究快照",
            type="primary",
            width="stretch",
        )
    st.caption(
        f"当前镜头日期：{selected_date.isoformat()}｜可调查范围："
        f"{timeline_min.isoformat()} — {timeline_max.isoformat()}"
    )

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
        width="stretch",
        config={"displaylogo": False},
    )
    st.caption(
        "图表在历史截止线处结束，不包含截止日之后的价格。"
        "Historical Lens 默认使用不复权价格，避免后来复权因子进入过去。"
    )

    _show_verified_financial_history(company, selected_date)

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
        evidence_records = _announcement_evidence_records(announcements)
        evidence_result = filter_evidence_as_of(
            evidence_records,
            selected_date,
        )
        evidence_chain = build_event_evidence_chain(
            evidence_records,
            selected_date,
        )
        _show_event_evidence_chain(
            evidence_chain,
            event_context=(
                prefill_context
                if isinstance(prefill_context, str)
                else None
            ),
        )
        st.markdown("#### 其他当时已知的官方证据")
        accepted = evidence_result["accepted"]
        matched_source_ids = {
            item["source_id"] for item in evidence_chain["matches"]
        }
        other_accepted = [
            record
            for record in accepted
            if record["source_id"] not in matched_source_ids
        ]
        if not accepted:
            st.info("当前查询范围内，没有取得截止日前可展示的官方公告。")
        elif not other_accepted:
            st.info("当前可展示的官方公告已全部列入上方证据链。")
        for record in other_accepted[:8]:
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
                    st.link_button(
                        "查看原文 ↗",
                        record["source_url"],
                        width="stretch",
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

    if historical_mission_active:
        mission_event = next(
            (
                event
                for event in flagship_events
                if event["event_id"]
                == HISTORICAL_GAME_MISSION["answer_event_id"]
            ),
            None,
        )
        mission_completed = (
            st.session_state.get("historical_game_mission_completed")
            == HISTORICAL_MISSION_ID
        )
        date_boundary_completed = (
            st.session_state.get(
                "historical_game_mission_date_completed"
            )
            == HISTORICAL_MISSION_ID
            or mission_completed
        )
        clock_boundary = None
        if mission_event is not None:
            try:
                clock_boundary = resolve_historical_mission_clock_boundary(
                    market_frame["date"].tolist(),
                    mission_event["published_date"],
                )
            except ValueError:
                clock_boundary = None
        st.divider()
        with st.container(border=True):
            st.caption("调查结论提交 · NO LIFE LOST")
            st.markdown("#### 第一步｜锁定目标证据的首次可见日")
            st.write(
                f"你当前锁定：**{selected_date.isoformat()}**。先检查上方"
                "官方证据和实际采用交易日，再提交结论。"
            )
            if mission_event is None:
                st.warning(
                    "任务所需的已核验事件暂时无法读取，本次不允许盲猜提交。"
                )
            elif mission_event["published_date"] <= selected_date:
                st.success(
                    "边界传感器：目标回购方案已经进入当前时点的官方证据集。"
                    "它是否刚刚出现，需要继续与前一日比较。"
                )
            else:
                st.info(
                    "边界传感器：目标回购方案尚未进入当前时点的官方证据集。"
                    "它可能尚未公开，也可能需要继续向后调查。"
                )
            if (
                mission_event is not None
                and not date_boundary_completed
                and st.button(
                    "锁定当前日期为调查答案",
                    type="primary",
                    width="stretch",
                    key=(
                        "submit_historical_game_mission_"
                        f"{selected_date.isoformat()}"
                    ),
                )
            ):
                evaluation = evaluate_historical_mission_date(
                    selected_date,
                    mission_event["published_date"],
                )
                if evaluation["is_correct"]:
                    st.session_state[
                        "historical_game_mission_date_completed"
                    ] = (
                        HISTORICAL_MISSION_ID
                    )
                    st.session_state["historical_game_mission_answer"] = (
                        selected_date.isoformat()
                    )
                    st.session_state[
                        "historical_game_mission_reasoning_attempt"
                    ] = 0
                    st.rerun()
                else:
                    st.warning(evaluation["feedback"])

            if date_boundary_completed and not mission_completed:
                st.success(
                    "第一步通过｜你已经找到目标证据第一次进入历史快照的"
                    "日期。找到日期还不等于理解时间边界，请完成最后判断。"
                )

                if clock_boundary is None:
                    st.warning(
                        "当前行情不足，无法同时核验公告前后两个交易时点。"
                        "本次不允许盲猜，也不会扣除生命。"
                    )
                else:
                    attempt_index = int(
                        st.session_state.get(
                            "historical_game_mission_reasoning_attempt",
                            0,
                        )
                    )
                    reasoning_question = (
                        build_historical_mission_reasoning_question(
                            clock_boundary,
                            attempt_index,
                        )
                    )
                    reasoning_feedback = st.session_state.pop(
                        "historical_game_mission_reasoning_feedback",
                        None,
                    )
                    if isinstance(reasoning_feedback, str):
                        st.warning(reasoning_feedback)

                    st.markdown("#### 第二步｜对齐两只时钟")
                    st.caption(
                        "请同时核对证据公开日、页面实际采用交易日，以及"
                        "行情时钟下一次跳动的日期。六项答案只有一项完整"
                        "守住时间与因果边界。"
                    )
                    with st.form(
                        key=reasoning_question["question_id"],
                        border=True,
                    ):
                        st.write(reasoning_question["prompt"])
                        selected_reasoning = st.radio(
                            "选择唯一完整且严谨的调查结论",
                            options=reasoning_question["options"],
                            index=None,
                            key=(
                                "historical_game_mission_reasoning_answer_"
                                f"{attempt_index}"
                            ),
                        )
                        reasoning_submitted = st.form_submit_button(
                            "提交最终调查结论",
                            type="primary",
                            width="stretch",
                        )

                    if reasoning_submitted:
                        if selected_reasoning is None:
                            st.warning("请先选择一项结论。空白提交不会扣除生命。")
                        else:
                            reasoning_evaluation = (
                                evaluate_historical_mission_reasoning(
                                    selected_reasoning,
                                    reasoning_question,
                                )
                            )
                            if reasoning_evaluation["is_correct"]:
                                st.session_state[
                                    "historical_game_mission_completed"
                                ] = HISTORICAL_MISSION_ID
                                st.session_state[
                                    "historical_game_mission_reasoning"
                                ] = selected_reasoning
                                st.session_state["cash_case_stage"] = (
                                    "migration_completed"
                                )
                                st.rerun()
                            st.session_state[
                                "historical_game_mission_reasoning_attempt"
                            ] = attempt_index + 1
                            st.session_state[
                                "historical_game_mission_reasoning_feedback"
                            ] = reasoning_evaluation["feedback"]
                            st.rerun()

            if mission_completed:
                st.success(
                    "首案完整通关｜9月20日的复盘越过了信息截止线；"
                    "9月21日是证据公开日，行情仍停在9月20日，下一交易日"
                    "是9月23日。后续涨跌不能自动证明公告造成了变化。"
                )
                if st.button(
                    "带着调查结论返回研究员任务局",
                    width="stretch",
                    key="return_to_game_after_historical_mission",
                ):
                    _switch_page("game")

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
        width="stretch",
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
        "12 / 方法与审计 · METHODOLOGY",
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
            "Python计算；异常交易日扫描同样由固定规则完成。"
            "AI只允许基于已经核验的数字和原文证据生成解释，"
            "不得自行补充财务数字或把异常日改写成买卖信号。"
        )
    with st.container(border=True):
        st.subheader("Historical Lens 时间隔离")
        st.write(
            "历史回看只允许使用发布日期不晚于所选截止日的证据。"
            "当时可见信息与后来1、3、6个月表现由不同函数计算，"
            "防止把未来数据带回过去。异动—公告证据链只检查所选日期"
            "及此前六个自然日的官方披露，并保留日期间隔；"
            "时间接近不会被解释为股价变化的原因。"
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
            "本产品帮助个人投资者、初级分析人员和金融学生完成上市公司"
            "第一轮研究：从一个公司名称或股票代码开始，连接公开行情、"
            "公告和年报，计算关键指标，识别值得继续核验的问题，并输出"
            "附有来源、页码和证据缺口的研究底稿。它减少前期资料整理与"
            "重复计算，让研究过程更一致、更容易复核，但不替代商业数据库、"
            "专业判断或尽职调查，也不提供个性化投资建议。"
        )
    show_chinese_user_guide()
    show_product_footer()


def render_financial_trend_page() -> None:
    """Render audited cross-year trends for supported A-share cases."""
    apply_product_theme()
    show_compact_page_header(
        "09 / 财务趋势实验室 · FINANCIAL TREND LAB",
        "财务趋势实验室",
        "把多年官方年报放在同一口径下，观察收入、利润、经营现金和"
        "负债结构变化，并保留报告版本、公开日期和原始页码。",
    )

    try:
        catalog_audit = audit_financial_history_catalog()
    except ValueError as error:
        st.error(f"已核验公司接入清单未通过检查：{error}")
        show_product_footer()
        return
    verified_cases = catalog_audit["cases"]
    case_by_code = {
        case["company_code"]: case for case in verified_cases
    }

    company = _selected_company()
    if company is None:
        company = _company_identity_from_financial_case(verified_cases[0])
        _store_selected_company(company)
        st.info(
            "尚未选择公司，已载入首个已核验案例："
            f"{company['name']}。"
        )

    _show_company_banner(company)
    if company["code"] not in case_by_code:
        covered_names = "、".join(
            case["company_name"] for case in verified_cases
        )
        st.info(
            f"独立的多年年报页码基准目前覆盖{covered_names}。"
            "这是因为每个年度都需要逐页核验，并处理后来发生的追溯调整；"
            "其他公司不会用未经核验的网络数字填补。"
        )
        fallback_options = {
            f"{case['company_name']}｜{case['canonical_code']}": case
            for case in verified_cases
        }
        fallback_label = st.selectbox(
            "选择已核验公司",
            options=list(fallback_options),
            key="verified_financial_fallback_selector",
        )
        if st.button(
            "载入选择的已核验公司",
            type="primary",
            width="stretch",
        ):
            _store_selected_company(
                _company_identity_from_financial_case(
                    fallback_options[fallback_label]
                )
            )
            st.rerun()
        show_product_footer()
        return

    verified_company_options = {
        f"{case['company_name']}｜{case['canonical_code']}": case
        for case in verified_cases
    }
    option_labels = list(verified_company_options)
    current_label = next(
        label for label, case in verified_company_options.items()
        if case["company_code"] == company["code"]
    )
    selected_label = st.selectbox(
        "切换已核验公司",
        options=option_labels,
        index=option_labels.index(current_label),
        key="verified_financial_company_selector",
    )
    selected_case = verified_company_options[selected_label]
    selected_code = selected_case["company_code"]
    if selected_code != company["code"]:
        _store_selected_company(
            _company_identity_from_financial_case(selected_case)
        )
        st.rerun()

    st.success(
        "标准化接入检查通过："
        f"{catalog_audit['company_count']} 家公司｜"
        f"{catalog_audit['financial_period_count']} 个财务年度｜"
        f"{catalog_audit['publication_vintage_count']} 个公开报告版本。"
    )
    with st.expander("查看已核验公司接入清单"):
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "公司": case["company_name"],
                        "股票代码": case["canonical_code"],
                        "核验年度": (
                            f"{case['coverage_start_year']}—"
                            f"{case['coverage_end_year']}"
                        ),
                        "年度数": case["verified_periods"],
                        "最近复核": case["reviewed_on"].isoformat(),
                        "状态": "自动检查通过",
                    }
                    for case in verified_cases
                ]
            ),
            hide_index=True,
            width="stretch",
        )
        st.caption(
            "新增公司必须同时通过身份、连续年度、官方 HTTPS 来源、"
            "报告页码、金额和会计版本检查，才会自动出现在上方列表。"
        )

    try:
        result = select_financial_history_as_of(
            load_verified_financial_history(company["code"]),
            date.today(),
        )
        review = build_financial_trend_review(result["points"])
    except ValueError as error:
        st.warning(str(error))
        show_product_footer()
        return

    summary_columns = st.columns(4)
    summary_columns[0].metric(
        "已核验年度",
        f"{review['period_count']}个",
        f"{review['start_year']}—{review['end_year']}",
        delta_color="off",
    )
    summary_columns[1].metric(
        "营业收入复合年变化",
        _format_percent(review["revenue_cagr"]),
        "只使用首末已核验年度",
        delta_color="off",
    )
    summary_columns[2].metric(
        "归母净利润复合年变化",
        _format_percent(review["net_profit_cagr"]),
        "只使用首末已核验年度",
        delta_color="off",
    )
    summary_columns[3].metric(
        "经营现金流复合年变化",
        _format_percent(review["operating_cash_flow_cagr"]),
        "只使用首末已核验年度",
        delta_color="off",
    )
    st.caption(
        "复合年变化率使用首个与最后一个已核验完整年度计算，"
        "不会把中间波动隐藏成未来预测。"
    )

    st.subheader("跨年结构观察")
    structure_columns = st.columns(3)
    with structure_columns[0]:
        with st.container(border=True):
            st.markdown("#### 收入—利润")
            st.write(review["growth_alignment"])
            st.caption("比较最新年度收入与归母净利润同比方向。")
    with structure_columns[1]:
        with st.container(border=True):
            st.markdown("#### 利润—经营现金")
            st.write(review["cash_alignment"])
            st.caption("比较最新年度利润与经营现金流同比方向。")
    with structure_columns[2]:
        with st.container(border=True):
            st.markdown("#### 报告版本审计")
            st.write(f"追溯调整版本 {review['restatement_count']} 个")
            st.caption("调整后的历史数字只从其公开日期起生效。")

    for observation in review["observations"]:
        st.markdown(f"- {observation}")
    st.warning(review["limitation"])

    _show_verified_financial_history(company, date.today())
    show_product_footer()


def render_financial_anomaly_explanation_page() -> None:
    """Explain one verified financial divergence through a cash-flow bridge."""
    apply_product_theme()
    show_compact_page_header(
        "11 / 财务异常解释 · FINANCIAL EXPLANATION AGENT",
        "财务异常解释 Agent",
        "从“指标为什么不同向”出发，用已核验年报逐项勾稽；"
        "已证实的算术桥接与待核查的业务原因分开展示。",
    )

    try:
        reviews = []
        for components in load_financial_anomaly_cases():
            company_code = components[0]["company_code"]
            points = select_financial_history_as_of(
                load_verified_financial_history(company_code),
                date.today(),
            )["points"]
            reviews.append(
                build_financial_anomaly_review(points, components)
            )
    except ValueError as error:
        st.error(f"财务异常证据未通过检查：{error}")
        show_product_footer()
        return

    case_options = {
        (
            f"{item['company_name']}｜{item['canonical_code']}｜"
            f"{item['period_year']} 年经营现金流背离"
        ): item
        for item in reviews
    }
    selected_case = st.selectbox(
        "选择已核验异常案例",
        options=list(case_options),
        key="financial_anomaly_case_selector",
    )
    review = case_options[selected_case]
    st.info(
        f"当前收录 {len(reviews)} 个受控案例："
        + "、".join(
            f"{item['company_name']} {item['period_year']} 年"
            for item in reviews
        )
        + "。"
        "运行时不下载整份 PDF，不需要付费 API。"
    )

    signal_columns = st.columns(3)
    signal_columns[0].metric(
        "营业收入同比",
        _format_percent(review["revenue_growth"]),
        "已核验趋势数据",
        delta_color="off",
    )
    signal_columns[1].metric(
        "归母净利润同比",
        _format_percent(review["attributable_net_profit_growth"]),
        "已核验趋势数据",
        delta_color="off",
    )
    signal_columns[2].metric(
        "经营现金流同比",
        _format_percent(review["operating_cash_flow_growth"]),
        "已核验趋势数据",
        delta_color="off",
    )
    if review["signal_detected"]:
        st.warning(f"规则识别：**{review['signal_label']}**。")
    else:
        st.info(f"规则识别：{review['signal_label']}。")

    st.subheader("四步解释链")
    trace_columns = st.columns(4)
    trace_items = (
        ("① 异常扫描", "方向背离规则已触发"),
        (
            "② 年报勾稽",
            f"{len(review['drivers'])} 项调节数据与经营现金一致",
        ),
        ("③ 贡献排名", "按同比影响绝对值排序"),
        ("④ 边界审计", "业务原因留在待核查区"),
    )
    for column, (title, text) in zip(
        trace_columns,
        trace_items,
        strict=True,
    ):
        with column:
            with st.container(border=True):
                st.markdown(f"#### {title}")
                st.caption(text)

    st.subheader("已证实｜现金流桥接")
    for finding in review["confirmed_findings"]:
        st.markdown(f"- {finding}")
    st.success(
        "勾稽通过："
        f"{review['period_year']} 年 "
        f"{_format_optional_cny_100m(review['bridge_current_total'])}｜"
        f"{review['comparison_year']} 年 "
        f"{_format_optional_cny_100m(review['bridge_comparison_total'])}｜"
        "同比变化 "
        f"{_format_optional_cny_100m(review['bridge_change_total'])}。"
    )

    driver_rows = [
        {
            "排名": driver["rank"],
            "现金流调节项": driver["component_label"],
            "对同比变化的方向": driver["direction"],
            f"{review['comparison_year']}（亿元）": round(
                driver["comparison_value"] / 100_000_000,
                2,
            ),
            f"{review['period_year']}（亿元）": round(
                driver["current_value"] / 100_000_000,
                2,
            ),
            "同比贡献（亿元）": round(
                driver["change_contribution"] / 100_000_000,
                2,
            ),
        }
        for driver in review["drivers"]
    ]
    st.dataframe(
        pd.DataFrame(driver_rows),
        hide_index=True,
        width="stretch",
    )
    st.caption(
        "“同比贡献”是各调节项当期值减上年值。"
        "负数表示拉低经营现金流的同比变化，不等于利空。"
    )

    st.subheader("待进一步核查｜不冒充已证实原因")
    for question in review["unresolved_questions"]:
        st.markdown(f"- {question}")

    with st.container(border=True):
        source_column, action_column = st.columns([4, 1])
        with source_column:
            st.markdown(f"**{review['report_title']}**")
            st.caption(
                f"年报第 {review['source_page']} 页｜"
                f"证据等级 {review['evidence_grade']}｜"
                "人工核验通过｜原报告单位千元，页面统一换算为元"
            )
        with action_column:
            st.link_button(
                "查看官方年报 ↗",
                review["source_url"],
                width="stretch",
            )

    report_html = build_financial_anomaly_report_html(review)
    st.download_button(
        "下载财务异常解释报告（HTML）",
        data=report_html.encode("utf-8"),
        file_name=(
            f"{review['company_code']}_{review['period_year']}"
            "_financial_anomaly_explanation.html"
        ),
        mime="text/html",
        width="stretch",
    )
    st.warning(review["limitation"])
    show_product_footer()


def render_cross_company_comparison_page() -> None:
    """Render a common-year comparison with audited industry boundaries."""
    apply_product_theme()
    show_compact_page_header(
        "10 / 跨公司横向比较 · CROSS-COMPANY COMPARISON",
        "跨公司横向比较工作台",
        "在共同财务年度下比较已核验的规模、增长、盈利、经营现金和"
        "负债结构，同时保留每家公司的官方年报页码。",
    )

    try:
        catalog_audit = audit_financial_history_catalog()
        industry_audit = audit_company_industry_catalog(
            catalog_audit["cases"]
        )
    except ValueError as error:
        st.error(f"公司或行业接入清单未通过检查：{error}")
        show_product_footer()
        return

    industry_profiles = industry_audit["profiles"]
    industry_by_code = {
        profile["company_code"]: profile
        for profile in industry_profiles
    }

    case_options = {
        f"{case['company_name']}｜{case['canonical_code']}": case
        for case in catalog_audit["cases"]
    }
    selected_labels = st.multiselect(
        "选择比较公司（至少2家）",
        options=list(case_options),
        default=list(case_options),
        key="cross_company_comparison_selector",
    )
    if len(selected_labels) < 2:
        st.info("请至少选择两家已核验公司，才能建立共同年度比较。")
        show_product_footer()
        return

    selected_cases = [case_options[label] for label in selected_labels]
    points_by_code = {}
    cutoff = date.today()
    try:
        for case in selected_cases:
            result = select_financial_history_as_of(
                load_verified_financial_history(case["company_code"]),
                cutoff,
            )
            points_by_code[case["company_code"]] = result["points"]
        initial_comparison = build_cross_company_comparison(
            selected_cases,
            points_by_code,
            industry_profiles=industry_profiles,
        )
    except ValueError as error:
        st.warning(str(error))
        show_product_footer()
        return

    year_options = sorted(
        initial_comparison["common_years"],
        reverse=True,
    )
    selection_signature = "_".join(
        case["company_code"] for case in selected_cases
    )
    selected_year = st.selectbox(
        "共同财务年度",
        options=year_options,
        index=0,
        key=f"cross_company_comparison_year_{selection_signature}",
    )
    comparison = build_cross_company_comparison(
        selected_cases,
        points_by_code,
        selected_year,
        industry_profiles=industry_profiles,
    )
    rows = comparison["rows"]

    if comparison["is_same_peer_group"]:
        st.success(
            f"行业边界检查通过：**{comparison['scope_label']}**。"
            "这只是同行组候选，仍需继续核查业务分部和会计口径。"
        )
    else:
        st.warning(
            f"当前选择覆盖 {comparison['industry_group_count']} 个研究同行组，"
            f"因此属于 **{comparison['scope_label']}**。"
            "页面不会生成跨行业综合优劣分数。"
        )
    st.success(
        "共同年度检查通过："
        f"{comparison['company_count']} 家公司｜"
        f"{comparison['selected_year']} 财务年度｜"
        f"{len(rows)} 份 A 级官方年报证据。"
    )

    st.subheader("行业证据与同行组状态")
    st.caption(
        "披露行业来自公司官方年报；研究同行组是本产品为可比性建立的"
        "更窄标签，不等同于监管机构的估值分类。"
    )
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "公司": case["company_name"],
                    "年报披露行业": industry_by_code[
                        case["company_code"]
                    ]["disclosed_industry"],
                    "研究同行组": industry_by_code[
                        case["company_code"]
                    ]["peer_group_name"],
                    "分类依据": industry_by_code[
                        case["company_code"]
                    ]["classification_basis"],
                    "年报证据页": industry_by_code[
                        case["company_code"]
                    ]["source_page"],
                    "证据等级": industry_by_code[
                        case["company_code"]
                    ]["evidence_grade"],
                }
                for case in selected_cases
            ]
        ),
        hide_index=True,
        width="stretch",
    )
    st.markdown("#### 已核验同行组覆盖")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "研究同行组": coverage["peer_group_name"],
                    "已核验公司": "、".join(coverage["company_names"]),
                    "公司数量": coverage["company_count"],
                    "同行候选状态": (
                        "可用"
                        if coverage["ready"]
                        else f"尚缺 {coverage['companies_needed']} 家"
                    ),
                }
                for coverage in industry_audit["coverage"]
            ]
        ),
        hide_index=True,
        width="stretch",
    )
    ready_groups = [
        coverage["peer_group_name"]
        for coverage in industry_audit["coverage"]
        if coverage["ready"]
    ]
    if ready_groups:
        st.success(
            "已建立同行组候选覆盖："
            + "、".join(ready_groups)
            + "。选择同组公司后，页面仍会提醒继续核查业务分部和会计口径。"
        )
    else:
        st.info(
            "当前每个研究同行组只有 1 家已核验公司，因此尚无可称为"
            "同行组候选的组合。下一步需要为其中一个组补充至少 1 家公司，"
            "并按相同页码和单位规则核验多年年报。"
        )

    summary_columns = st.columns(4)
    summary_columns[0].metric("共同财务年度", str(selected_year))
    summary_columns[1].metric("比较公司", f"{len(rows)}家")
    summary_columns[2].metric("官方年报", f"{len(rows)}份")
    summary_columns[3].metric(
        "最近公开日期",
        max(row["published_date"] for row in rows),
    )

    st.subheader("同口径指标表")
    st.caption(
        "规模指标统一换算为人民币亿元；相对位置只与当前所选样本的"
        "中位数比较，不表示利好、利空或质量高低。"
    )
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "公司": row["company_name"],
                    "股票代码": row["canonical_code"],
                    "研究同行组": industry_by_code[
                        row["company_code"]
                    ]["peer_group_name"],
                    "营业收入（亿元）": round(
                        row["revenue"] / 100_000_000,
                        2,
                    ),
                    "归母净利润（亿元）": round(
                        row["net_profit"] / 100_000_000,
                        2,
                    ),
                    "经营现金（亿元）": round(
                        row["operating_cash_flow"] / 100_000_000,
                        2,
                    ),
                    "收入同比": _format_percent(row["revenue_growth"]),
                    "利润同比": _format_percent(row["net_profit_growth"]),
                    "经营现金同比": _format_percent(
                        row["operating_cash_flow_growth"]
                    ),
                    "归母净利率": _format_percent(row["net_margin"]),
                    "现金/利润": f"{row['cash_conversion']:.2f}倍",
                    "负债占资产": _format_percent(
                        row["liabilities_to_assets"]
                    ),
                    "净利率样本位置": row["net_margin_position"],
                    "负债率样本位置": row[
                        "liabilities_to_assets_position"
                    ],
                }
                for row in rows
            ]
        ),
        hide_index=True,
        width="stretch",
    )

    chart_columns = st.columns(2)
    with chart_columns[0]:
        st.markdown("#### 规模比较｜人民币亿元")
        scale_frame = pd.DataFrame(
            {
                row["company_name"]: {
                    "营业收入": row["revenue"] / 100_000_000,
                    "归母净利润": row["net_profit"] / 100_000_000,
                    "经营现金": row["operating_cash_flow"] / 100_000_000,
                }
                for row in rows
            }
        ).T
        st.bar_chart(scale_frame, height=330, width="stretch")
    with chart_columns[1]:
        st.markdown("#### 结构比较｜百分比")
        ratio_frame = pd.DataFrame(
            {
                row["company_name"]: {
                    "归母净利率": row["net_margin"] * 100,
                    "负债占总资产": row["liabilities_to_assets"] * 100,
                }
                for row in rows
            }
        ).T
        st.bar_chart(ratio_frame, height=330, width="stretch")

    st.markdown("#### 同比变化｜百分比")
    growth_frame = pd.DataFrame(
        {
            row["company_name"]: {
                "营业收入": (
                    row["revenue_growth"] * 100
                    if row["revenue_growth"] is not None
                    else None
                ),
                "归母净利润": (
                    row["net_profit_growth"] * 100
                    if row["net_profit_growth"] is not None
                    else None
                ),
                "经营现金": (
                    row["operating_cash_flow_growth"] * 100
                    if row["operating_cash_flow_growth"] is not None
                    else None
                ),
            }
            for row in rows
        }
    ).T
    st.bar_chart(growth_frame, height=330, width="stretch")
    st.caption(
        "三张图分别回答规模、结构和同比变化问题，避免把不同单位混进"
        "同一个综合得分。"
    )

    selected_peer_codes = {
        industry_by_code[row["company_code"]]["peer_group_code"]
        for row in rows
    }
    if comparison["is_same_peer_group"] and selected_peer_codes == {"baijiu"}:
        try:
            baijiu_records = load_baijiu_operating_quality()
        except ValueError as error:
            st.warning(f"白酒经营质量证据未通过检查：{error}")
        else:
            verified_baijiu_years = sorted(
                {
                    record["period_year"]
                    for record in baijiu_records
                }.intersection(comparison["common_years"])
            )
            if selected_year not in verified_baijiu_years:
                st.info(
                    "白酒经营质量增量指标已核验2023—2025年度；"
                    "更早年度仍保留通用横向比较，不混用未经复核的数据。"
                )
            else:
                try:
                    baijiu_quality = build_baijiu_operating_quality(
                        rows,
                        baijiu_records,
                    )
                    baijiu_history_rows = []
                    for history_year in verified_baijiu_years:
                        history_comparison = build_cross_company_comparison(
                            selected_cases,
                            points_by_code,
                            history_year,
                            industry_profiles=industry_profiles,
                        )
                        history_quality = build_baijiu_operating_quality(
                            history_comparison["rows"],
                            baijiu_records,
                        )
                        baijiu_history_rows.extend(history_quality["rows"])
                except ValueError as error:
                    st.warning(f"白酒经营质量证据未通过检查：{error}")
                else:
                    st.subheader(f"白酒经营质量透视｜{selected_year}")
                    st.caption(
                        "该面板只在已核验白酒同行组和共同年度下启用。"
                        "所有比率由 Python 根据合并年报原值计算，不生成综合分数。"
                    )
                    st.dataframe(
                        pd.DataFrame(
                            [
                                {
                                    "公司": row["company_name"],
                                    "合并毛利率": _format_percent(
                                        row["gross_margin"]
                                    ),
                                    "存货（亿元）": round(
                                        row["inventory"] / 100_000_000,
                                        2,
                                    ),
                                    "存货/总资产": _format_percent(
                                        row["inventory_to_assets"]
                                    ),
                                    "存货同比": _format_percent(
                                        row["inventory_growth"]
                                    ),
                                    "合同负债（亿元）": round(
                                        row["contract_liabilities"]
                                        / 100_000_000,
                                        2,
                                    ),
                                    "合同负债/收入": _format_percent(
                                        row[
                                            "contract_liabilities_to_revenue"
                                        ]
                                    ),
                                    "合同负债同比": _format_percent(
                                        row["contract_liabilities_growth"]
                                    ),
                                    "经营现金/归母净利": (
                                        f"{row['cash_conversion']:.2f}倍"
                                    ),
                                }
                                for row in baijiu_quality["rows"]
                            ]
                        ),
                        hide_index=True,
                        width="stretch",
                    )

                    st.markdown("#### 白酒结构指标｜百分比")
                    baijiu_ratio_frame = pd.DataFrame(
                        {
                            row["company_name"]: {
                                "合并毛利率": row["gross_margin"] * 100,
                                "存货/总资产": (
                                    row["inventory_to_assets"] * 100
                                ),
                                "合同负债/收入": (
                                    row[
                                        "contract_liabilities_to_revenue"
                                    ]
                                    * 100
                                ),
                            }
                            for row in baijiu_quality["rows"]
                        }
                    ).T
                    st.bar_chart(
                        baijiu_ratio_frame,
                        height=330,
                        width="stretch",
                    )
                    for observation in baijiu_quality["observations"]:
                        st.markdown(f"- {observation}")

                    history_start = min(verified_baijiu_years)
                    history_end = max(verified_baijiu_years)
                    st.markdown(
                        f"#### {history_start}—{history_end}经营质量趋势"
                    )
                    st.caption(
                        "每条线只连接同一公司的已审计年度数据；"
                        "趋势用于观察变化，不代表预测或质量排名。"
                    )

                    def _baijiu_history_frame(
                        field_name: str,
                    ) -> pd.DataFrame:
                        return (
                            pd.DataFrame(
                                [
                                    {
                                        "年度": row["period_year"],
                                        "公司": row["company_name"],
                                        "数值": row[field_name] * 100,
                                    }
                                    for row in baijiu_history_rows
                                ]
                            )
                            .pivot(
                                index="年度",
                                columns="公司",
                                values="数值",
                            )
                            .sort_index()
                        )

                    history_columns = st.columns(3)
                    history_specs = (
                        ("合并毛利率｜%", "gross_margin"),
                        ("存货/总资产｜%", "inventory_to_assets"),
                        (
                            "合同负债/收入｜%",
                            "contract_liabilities_to_revenue",
                        ),
                    )
                    for column, (label, field_name) in zip(
                        history_columns,
                        history_specs,
                    ):
                        with column:
                            st.markdown(f"##### {label}")
                            st.line_chart(
                                _baijiu_history_frame(field_name),
                                height=280,
                                width="stretch",
                            )

                    with st.expander(
                        "查看2023—2025历史指标的年报页码"
                    ):
                        st.dataframe(
                            pd.DataFrame(
                                [
                                    {
                                        "年度": row["period_year"],
                                        "公司": row["company_name"],
                                        "利润表页": row[
                                            "income_statement_page"
                                        ],
                                        "存货页": row["inventory_page"],
                                        "合同负债页": row[
                                            "contract_liabilities_page"
                                        ],
                                        "证据等级": row["evidence_grade"],
                                        "口径说明": row["notes"],
                                    }
                                    for row in baijiu_history_rows
                                ]
                            ),
                            hide_index=True,
                            width="stretch",
                        )
                    st.warning(baijiu_quality["limitation"])

    st.subheader("规则化观察")
    for observation in comparison["observations"]:
        st.markdown(f"- {observation}")

    with st.expander("查看共同年度的官方年报证据", expanded=True):
        basis_labels = {
            "original": "首次披露",
            "restated": "追溯调整后",
            "reported": "本期披露",
        }
        for row in rows:
            with st.container(border=True):
                evidence_text, evidence_link = st.columns([5, 1])
                with evidence_text:
                    st.markdown(
                        f"**{row['company_name']}｜{row['canonical_code']}｜"
                        f"{basis_labels[row['accounting_basis']]}**"
                    )
                    st.caption(
                        f"{row['report_title']}｜公开日期 "
                        f"{row['published_date']}｜主要数据第 "
                        f"{row['summary_page']} 页｜合并负债第 "
                        f"{row['balance_sheet_page']} 页｜证据等级 A"
                    )
                    if row["notes"]:
                        st.caption(row["notes"])
                with evidence_link:
                    st.link_button(
                        "查看年报 ↗",
                        row["source_url"],
                        width="stretch",
                    )

    st.warning(comparison["limitation"])
    st.caption(
        f"时间隔离审计：比较截止日为 {cutoff.isoformat()}；"
        "只有该日期以前已经公开的年报版本可以参与共同年度计算。"
    )
    show_product_footer()


def _process_onboarding_report(
    company: Mapping[str, object],
    report: AnnualReportCandidate,
) -> CandidateReportResult:
    """Process one report and release its large temporary objects immediately."""
    pdf_bytes: bytes | None = None
    extracted_pages: list[ExtractedPage] | None = None
    try:
        pdf_bytes = download_official_pdf(
            report["url"],
            max_bytes=32 * 1024 * 1024,
        )
        extracted_pages = extract_pdf_pages(pdf_bytes)
        return build_candidate_report_result(
            company,
            report,
            pdf_bytes,
            extracted_pages,
        )
    finally:
        # Never keep a complete annual report in Streamlit session state.
        del pdf_bytes, extracted_pages
        gc.collect()


def _show_onboarding_report_result(
    result: CandidateReportResult,
) -> None:
    """Show one compact extraction receipt without treating it as approval."""
    check_labels = {
        "income_statement_reconciled": "合并利润表",
        "balance_sheet_reconciled": "合并资产负债表",
        "cash_flow_statement_reconciled": "合并现金流量表",
    }
    check_columns = st.columns(3)
    for column, (key, label) in zip(
        check_columns,
        check_labels.items(),
        strict=True,
    ):
        if result["statement_checks"][key]:
            column.success(f"{label}：通过")
        else:
            column.warning(f"{label}：待复核")

    unit_check = result["unit_check"]
    if unit_check["passed"]:
        units = unit_check.get("units", [])
        st.caption(f"金额单位检查：通过｜{units[0] if units else '待核验'}")
    else:
        st.warning(str(unit_check["note"]))

    page_labels = {
        "income_statement": "利润表",
        "balance_sheet": "资产负债表",
        "cash_flow_statement": "现金流量表",
    }
    page_text = []
    for key, label in page_labels.items():
        page_range = result["statement_pages"].get(key)
        if page_range is None:
            page_text.append(f"{label}：未识别")
            continue
        start_page = page_range["start"]
        end_page = page_range["end"]
        pages = str(start_page) if start_page == end_page else (
            f"{start_page}–{end_page}"
        )
        page_text.append(f"{label}：PDF第{pages}页")
    st.caption("｜".join(page_text))

    value_labels = {
        "current_revenue": "营业收入",
        "current_net_profit": "归母/合并净利润",
        "current_operating_cash_flow": "经营现金流净额",
        "current_total_assets": "总资产",
        "current_total_liabilities": "总负债",
    }
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "财务年度": result["report_year"],
                    "指标": label,
                    "年报原始数值": result["values"].get(key),
                }
                for key, label in value_labels.items()
            ]
        ),
        hide_index=True,
        width="stretch",
    )
    st.caption(
        "PDF 指纹（SHA-256）："
        f"{result['evidence_fingerprint_sha256'][:16]}…｜"
        "用于识别本次证据文件，不是数字签名或第三方认证。"
    )


def render_company_onboarding_page() -> None:
    """Build a reviewable candidate package for one new audited company."""
    apply_product_theme()
    show_compact_page_header(
        "09 / 公司扩展 · ONBOARDING AGENT",
        "已核验公司扩展 Agent",
        "自动发现最近三份完整年报，逐份提取五项核心数据，并把页码、"
        "单位和跨年差异整理成人工复核候选包。",
    )
    st.info(
        "这项功能扩大的是“已核验深度案例层”，不是替代 Wind 的全市场数据库。"
        "系统不会未经人工确认就把候选数字写入正式目录。"
    )

    company = _selected_company()
    if company is None:
        st.markdown("### 选择候选公司")
        company = _render_company_search(
            key_prefix="audited_onboarding",
            navigate_on_success=False,
        )
    if company is None:
        st.caption("建议首个测试对象：美的集团（000333）。")
        show_product_footer()
        return

    _show_company_banner(company)
    if company["code"] in verified_financial_history_codes():
        st.warning(
            "该公司已经在已核验目录中。你仍可运行本流程检查最新报告，"
            "但结果只会作为更新候选包，不会覆盖现有数据。"
        )

    state_key = "audited_company_onboarding_state"
    notice_key = (
        "audited_company_onboarding_notice_"
        f"{company['canonical_code']}"
    )
    raw_state = st.session_state.get(state_key)
    if not isinstance(raw_state, dict) or (
        raw_state.get("canonical_code") != company["canonical_code"]
    ):
        raw_state = {
            "canonical_code": company["canonical_code"],
            "reports": [],
            "results": {},
        }
        st.session_state[state_key] = raw_state

    processing_notice = st.session_state.pop(notice_key, None)
    if isinstance(processing_notice, dict):
        notice_message = str(processing_notice.get("message", ""))
        if processing_notice.get("level") == "success":
            st.success(notice_message)
        else:
            st.warning(notice_message)

    st.markdown("### 第一步：建立三年年报候选任务")
    st.write(
        "Agent 只读取这家公司有限日期范围内的年报目录，排除摘要、半年报、"
        "问询和英文重复版本。此时不会下载 PDF。"
    )
    if st.button(
        "发现最近三份完整年报",
        type="primary",
        width="stretch",
        key=f"discover_onboarding_{company['canonical_code']}",
    ):
        end_date = date.today()
        start_date = end_date - timedelta(days=2_400)
        try:
            with st.spinner("正在读取官方年报目录……"):
                announcements = load_company_announcements(
                    company["code"],
                    start_date.isoformat(),
                    end_date.isoformat(),
                    "年报",
                )
                reports = select_recent_annual_reports(
                    announcements.to_dict("records")
                )
        except (DataSourceError, ValueError) as error:
            st.error(str(error))
        else:
            raw_state = {
                "canonical_code": company["canonical_code"],
                "reports": reports,
                "results": {},
            }
            st.session_state[state_key] = raw_state
            if len(reports) == 3:
                st.success("已建立最近三份完整年度报告的候选任务。")
            else:
                st.warning(
                    f"只找到 {len(reports)} 份可用完整年报；"
                    "候选包暂时不能通过连续三年检查。"
                )

    reports = raw_state.get("reports", [])
    results = raw_state.get("results", {})
    if not isinstance(reports, list) or not isinstance(results, dict):
        reports = []
        results = {}
    if not reports:
        st.caption(
            "先建立候选任务。公开目录暂不可用时，不会用搜索摘要或AI猜测补齐。"
        )
        show_product_footer()
        return

    typed_reports: list[AnnualReportCandidate] = reports
    typed_results: dict[str, CandidateReportResult] = results
    package = build_onboarding_package(
        company,
        typed_reports,
        typed_results,
    )
    processing = package["processing"]
    summary_columns = st.columns(4)
    summary_columns[0].metric("发现完整年报", f"{len(typed_reports)} / 3")
    summary_columns[1].metric(
        "已完成解析",
        f"{processing['processed_report_count']} / {len(typed_reports)}",
    )
    summary_columns[2].metric(
        "等待人工复核",
        str(processing["ready_for_human_review_count"]),
    )
    summary_columns[3].metric(
        "跨年差异线索",
        str(package["restatement_clue_count"]),
    )
    progress_value = (
        float(processing["processed_report_count"]) / len(typed_reports)
    )
    st.progress(
        progress_value,
        text="解析完成度只表示任务进度，不代表数据已经获准进入正式目录。",
    )

    st.markdown("### 第二步：逐份下载并核验")
    st.caption(
        "为保护 Render 免费服务器，每次只处理一份 PDF；解析完成后只保留"
        "五项数值、页码和文件指纹，不长期保存年报文件。"
    )
    report_options = {
        f"{report['report_year']}年｜{report['title']}": report
        for report in typed_reports
    }
    selected_label = st.selectbox(
        "选择本次核验的年度报告",
        options=list(report_options),
        key=f"onboarding_report_choice_{company['canonical_code']}",
    )
    selected_report = report_options[selected_label]
    process_columns = st.columns([1, 1])
    process_columns[0].link_button(
        "查看官方报告",
        selected_report["url"],
        width="stretch",
    )
    process_requested = process_columns[1].button(
        "下载并核验这一份年报",
        type="primary",
        width="stretch",
        key=(
            f"process_onboarding_{company['canonical_code']}_"
            f"{selected_report['report_year']}"
        ),
    )
    pending_reports = pending_annual_reports(typed_reports, typed_results)
    batch_requested = st.button(
        (
            "自动串行核验全部剩余报告"
            f"（{len(pending_reports)}份）"
        ),
        width="stretch",
        disabled=not pending_reports,
        key=f"process_all_onboarding_{company['canonical_code']}",
    )
    st.caption(
        "批量模式仍然一次只处理一份PDF；每份完成后立即释放原文件，"
        "同一浏览器会话内再次运行时会跳过已经成功的年度。"
    )
    if process_requested:
        try:
            with st.spinner(
                "正在临时下载PDF、核验三张报表并释放原始文件……"
            ):
                result = _process_onboarding_report(
                    company,
                    selected_report,
                )
        except (DataSourceError, ValueError) as error:
            st.error(str(error))
            st.info(
                "系统已停止本次接入。你可以打开官方报告确认它是否为扫描版、"
                "特殊行业报表，或文件是否超过免费服务器安全上限。"
            )
        else:
            typed_results[selected_report["url"]] = result
            raw_state["results"] = typed_results
            st.session_state[state_key] = raw_state
            if result["status"] == "ready_for_human_review":
                st.session_state[notice_key] = {
                    "level": "success",
                    "message": (
                        "三张报表和金额单位检查通过，已进入人工复核队列。"
                    ),
                }
            else:
                st.session_state[notice_key] = {
                    "level": "warning",
                    "message": (
                        "本报告存在未识别报表或单位问题，需要人工查看原文。"
                    ),
                }
            st.rerun()

    if batch_requested:
        batch_progress = st.progress(
            0.0,
            text="准备按年度逐份核验……",
        )
        failures: list[tuple[int, str]] = []
        completed_count = 0
        for index, report in enumerate(pending_reports, start=1):
            batch_progress.progress(
                (index - 1) / len(pending_reports),
                text=(
                    f"正在核验 {report['report_year']} 年报告｜"
                    f"第 {index} / {len(pending_reports)} 份"
                ),
            )
            try:
                result = _process_onboarding_report(company, report)
            except (DataSourceError, ValueError) as error:
                failures.append((report["report_year"], str(error)))
            else:
                typed_results[report["url"]] = result
                # Save each compact result before the next large PDF starts.
                raw_state["results"] = typed_results
                st.session_state[state_key] = raw_state
                completed_count += 1
            batch_progress.progress(
                index / len(pending_reports),
                text=f"已处理 {index} / {len(pending_reports)} 份",
            )

        raw_state["results"] = typed_results
        st.session_state[state_key] = raw_state
        if failures:
            failure_years = "、".join(
                f"{year}年" for year, _ in failures
            )
            st.session_state[notice_key] = {
                "level": "warning",
                "message": (
                    f"串行任务完成：成功 {completed_count} 份；"
                    f"{failure_years} 未通过，已保留给人工复核。"
                ),
            }
        else:
            st.session_state[notice_key] = {
                "level": "success",
                "message": (
                    f"已按顺序完成 {completed_count} 份年报核验；"
                    "全程一次只处理一份PDF。"
                ),
            }
        st.rerun()

    st.markdown("### 候选报告证据")
    for report in typed_reports:
        result = typed_results.get(report["url"])
        with st.container(border=True):
            title_column, link_column = st.columns([5, 1])
            title_column.markdown(
                f"#### {report['report_year']}年｜{report['title']}"
            )
            title_column.caption(
                f"公告日期：{report['published_date']}｜来源：巨潮资讯官方披露"
            )
            link_column.link_button(
                "原文 ↗",
                report["url"],
                width="stretch",
            )
            if result is None:
                st.info("等待逐份解析")
            else:
                _show_onboarding_report_result(result)

    package = build_onboarding_package(
        company,
        typed_reports,
        typed_results,
    )
    cross_checks = package["cross_report_checks"]
    if cross_checks:
        st.markdown("### 第三步：跨报告重述线索")
        changed_checks = [
            item
            for item in cross_checks
            if item["status"] == "changed_or_restated"
        ]
        if changed_checks:
            st.warning(
                "发现后续年报比较列与早期原始披露不一致。"
                "这可能是追溯调整或口径变化，不能直接当作错误。"
            )
        else:
            st.success("当前可比项目未发现跨报告数值变化。")
        metric_labels = {
            "revenue": "营业收入",
            "net_profit": "净利润",
            "operating_cash_flow": "经营现金流净额",
            "total_assets": "总资产",
            "total_liabilities": "总负债",
        }
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "财务年度": item["period_year"],
                        "指标": metric_labels[item["metric"]],
                        "首次披露": item["original_report_value"],
                        "后续比较列": item[
                            "later_report_comparative_value"
                        ],
                        "核验状态": {
                            "changed_or_restated": "存在差异，需查重述",
                            "unchanged": "一致",
                            "not_comparable": "单位或数据不可比",
                        }[item["status"]],
                    }
                    for item in cross_checks
                ]
            ),
            hide_index=True,
            width="stretch",
        )

    st.markdown("### 人工确认闸门")
    if package["status"] == "ready_for_human_review":
        st.success(
            "自动阶段完成：候选包可以交给人工逐项复核，但尚未进入正式目录。"
        )
    elif package["status"] == "human_review_required":
        st.warning("自动检查未全部通过，请先处理异常项。")
    elif package["status"] == "insufficient_report_history":
        st.warning("完整年报不足三份，暂不满足连续三年接入条件。")
    else:
        st.info("继续逐份解析，完成后再进入人工复核。")
    for action in package["approval_gate"]["required_actions"]:
        st.markdown(f"- {action}")

    st.download_button(
        "下载公司接入候选包（JSON）",
        data=serialise_onboarding_package(package),
        file_name=(
            f"{company['code']}_{company['name']}_audited_candidate.json"
        ),
        mime="application/json",
        width="stretch",
    )
    st.caption(
        "候选包明确记录 catalogue_written=false；下载不会自动修改网站数据库。"
    )
    if package["status"] == "ready_for_human_review":
        st.markdown("### 第四步：生成标准数据草稿")
        st.warning(
            "CSV 已按人民币元统一换算，但 verification_status 保持为 candidate。"
            "正式数据加载器会拒绝它，直至人工完成复核并明确批准。"
        )
        try:
            financial_history_draft = serialise_financial_history_draft(
                package
            )
        except ValueError as error:
            st.warning(str(error))
        else:
            st.download_button(
                "下载标准财务历史CSV草稿",
                data=financial_history_draft,
                file_name=(
                    f"{company['code']}_{company['name']}"
                    "_financial_history_candidate.csv"
                ),
                mime="text/csv",
                width="stretch",
            )
            st.caption(
                "该文件只减少手工整理工作，不代表公司已经进入已核验目录。"
            )
    show_product_footer()


def _format_snapshot_amount(value: object) -> str:
    """Format a normalised RMB amount without implying false precision."""
    if value is None:
        return "待核验"
    return f"¥{float(value) / 100_000_000:,.2f}亿"


def _format_snapshot_ratio(value: object) -> str:
    """Format one deterministic ratio or retain its evidence gap."""
    if value is None:
        return "待核验"
    return f"{float(value):.1%}"


def _format_snapshot_pages(pages: object) -> str:
    """Format an inclusive PDF page range from compact provenance."""
    if not isinstance(pages, Mapping):
        return "待核验"
    start = int(pages["start"])
    end = int(pages["end"])
    return str(start) if start == end else f"{start}–{end}"


def render_financial_snapshot_page() -> None:
    """Generate one temporary, page-linked snapshot for an A-share company."""
    apply_product_theme()
    show_compact_page_header(
        "财务 / 按需快照 · ON-DEMAND FINANCIAL SNAPSHOT",
        "全市场按需财务快照 Agent",
        "输入或选择普通A股公司后，系统临时取得最新完整年度报告，"
        "完成三表勾稽、金额单位校验和核心指标计算；只保留小型结果，"
        "不预先囤积全市场PDF。",
    )
    company = _selected_company()
    if company is None:
        st.warning("请先输入要生成财务快照的A股公司名称或6位代码。")
        company = _render_company_search(
            key_prefix="financial_snapshot",
            navigate_on_success=False,
        )
    if company is None:
        show_product_footer()
        return

    _show_company_banner(company)
    with st.container(border=True):
        st.markdown("#### 一次请求，完成五步资料整理")
        st.write(
            "核验公司身份 → 查找最新完整年报 → 临时下载PDF → "
            "勾稽三张报表 → 输出带原文页码的候选快照。"
        )
        st.caption(
            "只有点击按钮后才访问公开数据源。PDF不会写入项目仓库或"
            "服务器数据库；本页完成解析后只在当前会话保留结构化结果。"
        )
        generate_requested = st.button(
            "生成最新年报财务快照",
            type="primary",
            width="stretch",
            key=f"generate_financial_snapshot_{company['canonical_code']}",
        )

    if generate_requested:
        st.session_state.pop("on_demand_financial_snapshot", None)
        pdf_bytes: bytes | None = None
        extracted_pages: list[ExtractedPage] | None = None
        try:
            with st.spinner("正在定位最新完整年度报告……"):
                end_date = date.today()
                start_date = end_date - timedelta(days=550)
                announcements = load_company_announcements(
                    company["code"],
                    start_date.isoformat(),
                    end_date.isoformat(),
                    "年报",
                )
                latest_report = select_latest_annual_report(announcements)
                if latest_report is None:
                    raise ValueError(
                        "最近550天内没有找到可自动载入的完整年度报告。"
                    )
                report_candidates = select_recent_annual_reports(
                    [latest_report.to_dict()],
                    limit=1,
                )
                if not report_candidates:
                    raise ValueError(
                        "最新公告的报告期或官方来源未通过自动校验。"
                    )
                report = report_candidates[0]

            with st.spinner("正在临时下载年报并勾稽三张报表……"):
                # Keep the free service stable: this focused workflow does not
                # retain the PDF in a Streamlit cache and rejects oversized
                # source files before parsing them.
                pdf_bytes = download_official_pdf(
                    report["url"],
                    max_bytes=45 * 1024 * 1024,
                )
                extracted_pages = extract_pdf_pages(pdf_bytes)
                candidate_result = build_candidate_report_result(
                    company,
                    report,
                    pdf_bytes,
                    extracted_pages,
                )
                snapshot = build_on_demand_financial_snapshot(
                    company,
                    candidate_result,
                )
                st.session_state["on_demand_financial_snapshot"] = snapshot
        except (DataSourceError, ValueError) as error:
            st.error(str(error))
            st.info(
                "系统没有猜测缺失数值。你仍可进入“年报与证据”页面，"
                "通过官方链接下载后手工上传分析。"
            )
        except MemoryError:
            st.error(
                "该报告解析所需内存超过当前免费服务器的安全范围，"
                "系统已停止本次任务。"
            )
        finally:
            # Drop all request-local references.  The retained session object
            # contains only metrics, checks, page ranges and source metadata.
            extracted_pages = None
            pdf_bytes = None
            gc.collect()

    stored_snapshot = st.session_state.get("on_demand_financial_snapshot")
    snapshot: OnDemandFinancialSnapshot | None = None
    if (
        isinstance(stored_snapshot, dict)
        and isinstance(stored_snapshot.get("company"), dict)
        and stored_snapshot["company"].get("canonical_code")
        == company["canonical_code"]
    ):
        snapshot = stored_snapshot  # type: ignore[assignment]

    if snapshot is None:
        st.info(
            "尚未生成当前公司的快照。本功能面向普通A股年度报告；"
            "银行、保险、扫描版或特殊报表版式可能需要人工分析。"
        )
        st.warning(
            "自动提取结果只是候选数据，不是审计意见、估值结论或买卖建议。"
        )
        show_product_footer()
        return

    if snapshot["status"] == "ready_for_human_review":
        st.success(snapshot["status_label"])
    else:
        st.warning(snapshot["status_label"])

    report = snapshot["report"]
    with st.container(border=True):
        st.markdown("#### 官方来源与处理状态")
        st.write(str(report["title"]))
        st.caption(
            f"报告期：{report['report_year']}｜公告日："
            f"{report['published_date']}｜PDF共 {report['page_count']} 页。"
        )
        st.link_button(
            "查看官方年报原文",
            str(report["source_url"]),
            width="stretch",
        )
        st.caption(snapshot["unit_note"])

    st.subheader("三张报表自动勾稽")
    statement_labels = {
        "income_statement_reconciled": "利润表",
        "balance_sheet_reconciled": "资产负债表",
        "cash_flow_statement_reconciled": "现金流量表",
    }
    statement_columns = st.columns(3)
    for column, (key, label) in zip(
        statement_columns,
        statement_labels.items(),
    ):
        passed = snapshot["statement_checks"].get(key, False)
        column.metric(label, "通过" if passed else "待人工检查")

    st.subheader("核心财务快照")
    metric_columns = st.columns(3)
    for index, metric in enumerate(snapshot["metrics"]):
        delta = (
            None
            if metric["change_rate"] is None
            else f"同比/较上年末 {metric['change_rate']:+.1%}"
        )
        metric_columns[index % 3].metric(
            metric["label"],
            _format_snapshot_amount(metric["current_yuan"]),
            delta=delta,
            delta_color="off",
            help=(
                f"来源：{metric['statement']} PDF第"
                f"{_format_snapshot_pages(metric['pages'])}页。"
            ),
        )

    st.caption(
        "变化率使用最新年报内的比较栏计算；利润表和现金流量表是同比，"
        "资产负债表是较上年末。比较栏可能包含追溯调整。"
    )
    st.subheader("确定性比例")
    ratio_columns = st.columns(3)
    ratio_columns[0].metric(
        "净利率（同一提取口径）",
        _format_snapshot_ratio(snapshot["ratios"]["net_profit_margin"]),
    )
    ratio_columns[1].metric(
        "经营现金流 / 净利润",
        _format_snapshot_ratio(
            snapshot["ratios"]["operating_cash_conversion"]
        ),
    )
    ratio_columns[2].metric(
        "资产负债率",
        _format_snapshot_ratio(snapshot["ratios"]["liabilities_to_assets"]),
    )
    st.caption(
        "公式：净利率 = 净利润 ÷ 营业收入；现金利润比 = 经营活动现金流量"
        "净额 ÷ 净利润；资产负债率 = 负债总额 ÷ 资产总额。"
    )
    st.caption(
        "如果分母为0、数值缺失或三表未全部通过，系统显示“待核验”，"
        "不会用0代替缺失值。"
    )

    with st.expander("查看证据页码、文件指纹与使用边界"):
        for metric in snapshot["metrics"]:
            st.write(
                f"- {metric['label']}：本期 "
                f"{_format_snapshot_amount(metric['current_yuan'])}｜比较栏 "
                f"{_format_snapshot_amount(metric['previous_yuan'])}｜"
                f"{metric['statement']} PDF第"
                f"{_format_snapshot_pages(metric['pages'])}页"
            )
        st.code(snapshot["source_fingerprint_sha256"], language=None)
        for limitation in snapshot["limitations"]:
            st.write(f"- {limitation}")

    report_html = build_financial_snapshot_report_html(snapshot)
    st.download_button(
        "下载财务快照核验底稿（HTML）",
        data=report_html,
        file_name=(
            f"{company['code']}_{company['name']}_财务快照_"
            f"{report['report_year']}.html"
        ),
        mime="text/html",
        width="stretch",
    )
    st.warning(
        "自动提取候选，未经人工复核。请打开官方年报核对页码、合并口径"
        "和单位后再使用；本页不构成投资建议。"
    )
    show_product_footer()


def render_annual_report_page() -> None:
    """Render the existing PDF evidence workflow as a dedicated subpage."""
    apply_product_theme()
    show_compact_page_header(
        "08 / 年报与证据 · ANNUAL REPORT",
        "年报与证据分析",
        "上传公开年度报告，按页提取文字、计算财务指标并生成可追溯答案。",
    )
    company = _selected_company()
    if company is not None:
        _show_company_banner(company)
        if (
            company["code"] in verified_financial_history_codes()
            and st.button(
                "查看已核验多年财务趋势",
                width="stretch",
            )
        ):
            _switch_page("financial_trend")
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
                "年报",
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
                    width="stretch",
                )
                auto_load_requested = report_columns[1].button(
                    "自动载入并分析",
                    type="primary",
                    width="stretch",
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
            st.markdown("#### 三张报表自动核验")
            statement_columns = st.columns(3)
            statement_checks = (
                ("合并利润表", extracted_figures),
                ("合并资产负债表", balance_sheet_figures),
                ("合并现金流量表", cash_flow_figures),
            )
            for statement_column, (statement_name, figures) in zip(
                statement_columns,
                statement_checks,
            ):
                if figures is None:
                    statement_column.warning(f"{statement_name}：尚未识别")
                else:
                    statement_column.success(
                        f"{statement_name}：已核验\n\n"
                        f"PDF 第 {_statement_page_label(figures)} 页"
                    )
            if any(figures is None for _, figures in statement_checks):
                st.caption(
                    "系统只展示完成标签识别和勾稽验证的报表；"
                    "没有通过验证的数字不会被猜测补全。"
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
                value=False,
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
                    width="stretch",
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
                        width="stretch",
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
                    width="stretch",
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
                    "证据行：营业收入 / Revenue 与归母净利润 / "
                    "Profit for the year，PDF 第 "
                    f"{_statement_page_label(extracted_figures)} 页。"
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
                is_chinese_balance_sheet = (
                    balance_sheet_figures.get("statement_format")
                    == "chinese_a_share"
                )

                st.subheader("自动提取：流动性")
                if is_chinese_balance_sheet:
                    st.caption(
                        "Python 核对流动资产、非流动资产和资产总计，"
                        "并用流动资产减去流动负债计算净营运资金。"
                    )
                else:
                    st.caption(
                        "Python 将流动资源减去流动负债，并与报表中的"
                        "净流动负债行进行勾稽核对。"
                    )
                resources_column, liabilities_column = st.columns(2)
                resources_column.metric(
                    (
                        f"流动资产 ({liquidity_unit})"
                        if is_chinese_balance_sheet
                        else f"流动资源 ({liquidity_unit})"
                    ),
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
                    (
                        f"净营运资金 ({liquidity_unit})"
                        if is_chinese_balance_sheet
                        else f"净流动负债 ({liquidity_unit})"
                    ),
                    f"{net_current_position:,.0f}",
                )
                if is_chinese_balance_sheet:
                    st.caption(
                        "中国报表中的持有待售资产已经包含在流动资产"
                        f"合计内。本期流动资产合计：{current_resources:,.0f} "
                        f"{liquidity_unit}；上期流动比率："
                        f"{previous_liquidity_ratio:.2f}x。"
                    )
                else:
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
                if is_chinese_balance_sheet:
                    st.caption(
                        "证据行：流动资产合计、非流动资产合计、资产总计、"
                        "流动负债合计，PDF 第 "
                        f"{_statement_page_label(balance_sheet_figures)} 页。"
                    )
                else:
                    st.caption(
                        "证据行：Current assets、Non-current assets "
                        "classified as held for sale、Current liabilities "
                        "与 Net current liabilities，PDF 第 "
                        f"{_statement_page_label(balance_sheet_figures)} 页。"
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
                if is_chinese_balance_sheet:
                    st.caption(
                        "Python 分别验证流动与非流动项目之和，并核对"
                        "资产总计 = 负债合计 + 所有者权益合计。"
                    )
                else:
                    st.caption(
                        "Python 汇总流动与非流动项目，并验证总资产减"
                        "总负债等于报表净资产。"
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
                if is_chinese_balance_sheet:
                    st.caption(
                        "证据行：资产总计、负债合计与所有者权益合计，"
                        "PDF 第 "
                        f"{_statement_page_label(balance_sheet_figures)} 页。"
                    )
                else:
                    st.caption(
                        "证据部分：非流动资产、流动资源、流动负债、"
                        "非流动负债和净资产，PDF 第 "
                        f"{_statement_page_label(balance_sheet_figures)} 页。"
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
                is_chinese_cash_flow = (
                    cash_flow_figures.get("statement_format")
                    == "chinese_a_share"
                )

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
                    (
                        f"筹资活动现金流 ({cash_flow_unit})"
                        if is_chinese_cash_flow
                        else f"融资活动现金流 ({cash_flow_unit})"
                    ),
                    f"{financing_cash:,.0f}",
                )
                ending_cash_column.metric(
                    (
                        f"期末现金及现金等价物 ({cash_flow_unit})"
                        if is_chinese_cash_flow
                        else f"期末现金 ({cash_flow_unit})"
                    ),
                    f"{ending_cash:,.0f}",
                )
                if is_chinese_cash_flow:
                    st.caption(
                        f"现金流勾稽：{operating_cash:,.0f} + "
                        f"({investing_cash:,.0f}) + "
                        f"({financing_cash:,.0f}) + "
                        f"({exchange_effect:,.0f}) = "
                        f"{net_cash_change:,.0f} {cash_flow_unit} "
                        "现金及现金等价物净增加额。"
                    )
                    st.caption(
                        f"现金余额勾稽：{opening_cash:,.0f} + "
                        f"{net_cash_change:,.0f} = "
                        f"{ending_cash:,.0f} {cash_flow_unit}。"
                    )
                else:
                    st.caption(
                        f"现金流勾稽：{operating_cash:,.0f} + "
                        f"({investing_cash:,.0f}) + "
                        f"({financing_cash:,.0f}) = "
                        f"{net_cash_change:,.0f} {cash_flow_unit} "
                        "净现金变动。"
                    )
                    st.caption(
                        f"现金余额勾稽：{opening_cash:,.0f} + "
                        f"{net_cash_change:,.0f} + "
                        f"({exchange_effect:,.0f}) = "
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
                if is_chinese_cash_flow:
                    st.caption(
                        "证据行：经营、投资和筹资活动现金流量净额；"
                        "汇率影响；现金及现金等价物净增加额；期初与"
                        "期末余额，PDF 第 "
                        f"{_statement_page_label(cash_flow_figures)} 页。"
                    )
                else:
                    st.caption(
                        "证据行：经营、投资和融资净现金流；净现金变动；"
                        "期初与期末现金，PDF 第 "
                        f"{_statement_page_label(cash_flow_figures)} 页。"
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
            width="stretch",
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
            width="stretch",
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
            width="stretch",
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
            width="stretch",
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
        page_title="FANGZHENG AI｜金融研究实验室",
        page_icon="🔎",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _sync_browser_research_state()

    home_page = st.Page(
        render_home_page,
        title="首页",
        icon="🏠",
        default=True,
    )
    game_page = st.Page(
        render_game_hub_page,
        title="研究员任务局",
        icon="🧩",
    )
    research_terminal_page = st.Page(
        render_research_terminal_page,
        title="公司研究终端",
        icon="🔎",
    )
    workspace_page = st.Page(
        render_research_workspace_page,
        title="研究工具导航",
        icon="🗂️",
    )
    comprehensive_page = st.Page(
        render_comprehensive_research_page,
        title="一键综合研究 Agent",
        icon="🧠",
    )
    company_page = st.Page(
        render_company_research_page,
        title="公司研究中心",
        icon="🏢",
    )
    evidence_delta_page = st.Page(
        render_evidence_delta_page,
        title="证据增量 Agent",
        icon="🔎",
    )
    thesis_ledger_page = st.Page(
        render_research_thesis_page,
        title="研究结论账本",
        icon="📚",
    )
    market_page = st.Page(
        render_market_page,
        title="K线与市场表现",
        icon="📈",
    )
    volume_turnover_page = st.Page(
        render_volume_turnover_page,
        title="成交量与换手率",
        icon="📊",
    )
    limit_up_page = st.Page(
        render_limit_up_board_page,
        title="每日涨停板观察台",
        icon="🔥",
    )
    radar_page = st.Page(
        render_market_radar_page,
        title="自选股任务队列",
        icon="🛰️",
    )
    anomaly_page = st.Page(
        render_market_anomaly_page,
        title="市场异动 Agent",
        icon="📡",
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
    financial_snapshot_page = st.Page(
        render_financial_snapshot_page,
        title="按需财务快照 Agent",
        icon="⚡",
    )
    onboarding_page = st.Page(
        render_company_onboarding_page,
        title="已核验公司扩展 Agent",
        icon="🧾",
    )
    financial_trend_page = st.Page(
        render_financial_trend_page,
        title="财务趋势实验室",
        icon="🧮",
    )
    financial_anomaly_page = st.Page(
        render_financial_anomaly_explanation_page,
        title="财务异常解释 Agent",
        icon="🧩",
    )
    comparison_page = st.Page(
        render_cross_company_comparison_page,
        title="跨公司横向比较",
        icon="⚖️",
    )
    methodology_page = st.Page(
        render_methodology_page,
        title="方法与审计",
        icon="🧭",
    )
    st.session_state["_wfz_page_registry"] = {
        "home": home_page,
        "game": game_page,
        "research_terminal": research_terminal_page,
        "workspace": workspace_page,
        "comprehensive": comprehensive_page,
        "company": company_page,
        "evidence_delta": evidence_delta_page,
        "thesis_ledger": thesis_ledger_page,
        "market": market_page,
        "volume_turnover": volume_turnover_page,
        "limit_up": limit_up_page,
        "radar": radar_page,
        "anomaly": anomaly_page,
        "historical": historical_page,
        "financial_snapshot": financial_snapshot_page,
        "annual": annual_page,
        "onboarding": onboarding_page,
        "financial_trend": financial_trend_page,
        "financial_anomaly": financial_anomaly_page,
        "comparison": comparison_page,
        "methodology": methodology_page,
    }

    navigation = st.navigation(
        {
            "开始": [home_page],
            "两大模块": [game_page, research_terminal_page],
            "研究终端｜工具导航": [workspace_page],
            "研究终端｜发现与跟踪": [
                limit_up_page,
                radar_page,
            ],
            "研究终端｜公司主线": [
                comprehensive_page,
                company_page,
                evidence_delta_page,
                thesis_ledger_page,
            ],
            "研究终端｜市场与复盘": [
                market_page,
                volume_turnover_page,
                anomaly_page,
                historical_page,
            ],
            "研究终端｜财务与年报": [
                financial_snapshot_page,
                annual_page,
                financial_trend_page,
                comparison_page,
                financial_anomaly_page,
            ],
            "研究终端｜数据与方法": [onboarding_page, methodology_page],
        }
    )
    navigation.run()


if __name__ == "__main__":
    main()
