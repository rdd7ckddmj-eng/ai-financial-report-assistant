"""Bounded, auditable export for a validated ResearchCase v1.

The workpaper is deliberately a projection of the canonical ResearchCase,
not another mutable source of truth.  Formal export is available only when
the case's derived readiness is ``ready_to_export``.  The module has no UI,
filesystem, network, pandas or PDF dependency.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import json
from typing import Any

from .research_case import (
    QUESTION_KEYS,
    has_formal_evidence_reference,
    validate_research_case,
)


WORKPAPER_SCHEMA_VERSION = "1.0"
WORKPAPER_TYPE = "research_case_complete_workpaper"
MAX_WORKPAPER_BYTES = 500 * 1024


QUESTION_LABELS = {
    "recent_events": "近期发生了什么",
    "market_change": "市场表现发生了什么变化",
    "financial_quality": "财务质量最值得核验什么",
    "point_in_time": "在指定时点当时能够知道什么",
    "research_judgement": "当前研究判断及其边界是什么",
}


class ResearchCaseWorkpaperError(ValueError):
    """Raised when a case cannot safely become a formal workpaper."""


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as error:
        raise ResearchCaseWorkpaperError(
            "研究底稿只能包含标准JSON值，不得包含PDF或其他二进制本体。"
        ) from error


def _json_size(value: object) -> int:
    return len(_canonical_json(value).encode("utf-8"))


def _normalise_exported_at(value: datetime | str | None) -> str:
    candidate: datetime
    if value is None:
        candidate = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        candidate = value
    else:
        try:
            candidate = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as error:
            raise ResearchCaseWorkpaperError("导出时间必须是ISO日期时间。") from error
    if candidate.tzinfo is None:
        candidate = candidate.replace(tzinfo=timezone.utc)
    return candidate.astimezone(timezone.utc).isoformat(timespec="seconds")


def _build_epistemic_index(case: Mapping[str, object]) -> dict[str, object]:
    evidence = case["evidence"]
    hypotheses = case["hypotheses"]
    artifacts = case["artifacts"]
    brief = case["case_brief"]

    reviewed_fact_ids = [
        item["evidence_id"]
        for item in evidence
        if item["review_status"] in {"confirmed", "corrected"}
    ]
    other_source_ids = [
        item["evidence_id"]
        for item in evidence
        if item["review_status"] not in {"confirmed", "corrected"}
    ]
    return {
        "facts": {
            "classification": "fact",
            "reviewed_evidence_ids": reviewed_fact_ids,
            "meaning": "仅指已确认或已更正的来源记录，不把AI摘要自动升级为事实。",
        },
        "inferences": {
            "classification": "inference",
            "hypothesis_ids": [item["hypothesis_id"] for item in hypotheses],
            "meaning": "研究假设与判断仍属于推断，即使已有部分证据支持。",
        },
        "analysis_outputs": {
            "classification": "analysis_output",
            "artifact_ids": [item["artifact_id"] for item in artifacts],
            "meaning": "模块产物是分析工作结果，不等于来源事实。",
        },
        "unknowns": {
            "classification": "unknown",
            "unknown_ids": [item["unknown_id"] for item in brief["unknowns"]],
        },
        "contradictions": {
            "classification": "contradiction",
            "contradiction_ids": [
                item["contradiction_id"] for item in brief["contradictions"]
            ],
            "empty_state_meaning": "尚未记录可引用的矛盾，不代表证据已经一致。",
        },
        "other_source_records": {
            "classification": "source_record_not_promoted_to_fact",
            "evidence_ids": other_source_ids,
        },
    }


def _responsible_ai_controls(case: Mapping[str, object]) -> dict[str, object]:
    historical = case["scope"]["mode"] == "historical"
    return {
        "canonical_case_validated": True,
        "formal_export_requires_ready_to_export": True,
        "formal_export_requires_cited_source_evidence": True,
        "ai_may_invent_numeric_values": False,
        "source_urls_and_available_pages_preserved": True,
        "historical_cutoff_enforced_by_case_contract": historical,
        "historical_cutoff_control": (
            "enforced" if historical else "not_applicable_to_current_case"
        ),
        "review_statuses_preserved": True,
        "failures_must_be_explicit": True,
        "human_review_remains_required": True,
        "source_pdf_or_binary_embedded": False,
        "investment_advice_generated": False,
    }


def build_research_case_workpaper(
    case: Mapping[str, object],
    *,
    exported_at: datetime | str | None = None,
) -> dict[str, Any]:
    """Build a formal workpaper from one export-ready ResearchCase.

    There is intentionally no silent draft mode: callers must show the live
    case in the product until the canonical readiness gate opens.
    """
    validate_research_case(case)
    if not has_formal_evidence_reference(case):
        raise ResearchCaseWorkpaperError(
            "正式研究工作底稿至少需要一条通过案件契约校验的真实证据引用。"
        )
    if case.get("readiness") != "ready_to_export":
        raise ResearchCaseWorkpaperError(
            "研究案件尚未达到ready_to_export，不能生成正式研究工作底稿。"
        )

    source_case = deepcopy(dict(case))
    case_json = _canonical_json(source_case)
    workpaper: dict[str, Any] = {
        "schema_version": WORKPAPER_SCHEMA_VERSION,
        "workpaper_type": WORKPAPER_TYPE,
        "workpaper_id": (
            f"research-case-workpaper:{case['case_id']}:r{case['revision']}"
        ),
        "exported_at": _normalise_exported_at(exported_at),
        "source_case_sha256": sha256(case_json.encode("utf-8")).hexdigest(),
        "research_case": source_case,
        "epistemic_index": _build_epistemic_index(source_case),
        "responsible_ai_controls": _responsible_ai_controls(source_case),
    }
    _validate_workpaper(workpaper)
    return workpaper


def _validate_workpaper(workpaper: Mapping[str, object]) -> None:
    required = {
        "schema_version",
        "workpaper_type",
        "workpaper_id",
        "exported_at",
        "source_case_sha256",
        "research_case",
        "epistemic_index",
        "responsible_ai_controls",
    }
    if set(workpaper) != required:
        raise ResearchCaseWorkpaperError("研究底稿字段不完整或包含未知字段。")
    if workpaper.get("schema_version") != WORKPAPER_SCHEMA_VERSION:
        raise ResearchCaseWorkpaperError("研究底稿schema版本不受支持。")
    if workpaper.get("workpaper_type") != WORKPAPER_TYPE:
        raise ResearchCaseWorkpaperError("研究底稿类型不受支持。")
    _normalise_exported_at(str(workpaper.get("exported_at", "")))
    case = workpaper.get("research_case")
    if not isinstance(case, Mapping):
        raise ResearchCaseWorkpaperError("研究底稿缺少规范研究案件。")
    validate_research_case(case)
    if not has_formal_evidence_reference(case):
        raise ResearchCaseWorkpaperError(
            "正式研究底稿缺少通过案件契约校验的真实证据引用。"
        )
    if case.get("readiness") != "ready_to_export":
        raise ResearchCaseWorkpaperError("正式研究底稿的案件状态不再可导出。")
    expected_id = f"research-case-workpaper:{case['case_id']}:r{case['revision']}"
    if workpaper.get("workpaper_id") != expected_id:
        raise ResearchCaseWorkpaperError("研究底稿编号与案件revision不匹配。")
    canonical_case = _canonical_json(case)
    expected_hash = sha256(canonical_case.encode("utf-8")).hexdigest()
    if workpaper.get("source_case_sha256") != expected_hash:
        raise ResearchCaseWorkpaperError("研究底稿中的案件内容与指纹不匹配。")
    if workpaper.get("epistemic_index") != _build_epistemic_index(case):
        raise ResearchCaseWorkpaperError("事实、推断、未知与矛盾索引不匹配。")
    if workpaper.get("responsible_ai_controls") != _responsible_ai_controls(case):
        raise ResearchCaseWorkpaperError("负责任AI控制字段不匹配。")
    if _json_size(workpaper) > MAX_WORKPAPER_BYTES:
        raise ResearchCaseWorkpaperError(
            f"研究底稿超过{MAX_WORKPAPER_BYTES}字节上限。"
        )


def serialise_research_case_workpaper(workpaper: Mapping[str, object]) -> str:
    """Return stable, human-readable UTF-8 JSON after integrity checks."""
    _validate_workpaper(workpaper)
    return json.dumps(
        workpaper,
        ensure_ascii=False,
        allow_nan=False,
        indent=2,
        sort_keys=True,
    )


def _h(value: object) -> str:
    return escape(str(value if value is not None else ""), quote=True)


def _json_html(value: object) -> str:
    rendered = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        indent=2,
        sort_keys=True,
    )
    return escape(rendered, quote=True)


def _refs_html(container: Mapping[str, object]) -> str:
    artifact_ids = container.get("artifact_ids", [])
    evidence_ids = container.get("evidence_ids", [])
    refs = [*(f"产物 {_h(item)}" for item in artifact_ids), *(f"证据 {_h(item)}" for item in evidence_ids)]
    return "；".join(refs) if refs else "未引用"


def render_research_case_workpaper_html(
    workpaper: Mapping[str, object],
) -> str:
    """Render a self-contained safe HTML view; every dynamic value is escaped."""
    _validate_workpaper(workpaper)
    case = workpaper["research_case"]
    company = case["company"]
    scope = case["scope"]
    brief = case["case_brief"]

    lane_rows = "".join(
        "<tr>"
        f"<th>{_h(QUESTION_LABELS[key])}</th>"
        f"<td>{_h(case['questions'][key]['status'])}</td>"
        f"<td>{_h(case['questions'][key]['summary'])}</td>"
        f"<td>{_h(case['questions'][key]['next_action'])}</td>"
        f"<td>{_refs_html(case['questions'][key])}</td>"
        "</tr>"
        for key in QUESTION_KEYS
    )

    contradictions = brief["contradictions"]
    if contradictions:
        contradiction_html = "<ul>" + "".join(
            f"<li><b>{_h(item['contradiction_id'])}</b>："
            f"{_h(item['summary'])}<br><small>{_refs_html(item)}</small></li>"
            for item in contradictions
        ) + "</ul>"
    else:
        contradiction_html = (
            '<p class="caution">当前尚未记录可引用的矛盾；'
            "这不代表证据已经一致。</p>"
        )
    unknown_html = (
        "<ul>"
        + "".join(
            f"<li><b>{_h(item['unknown_id'])}</b>：{_h(item['summary'])}</li>"
            for item in brief["unknowns"]
        )
        + "</ul>"
        if brief["unknowns"]
        else "<p>当前案件未登记未知项。</p>"
    )

    evidence_rows = "".join(
        "<tr>"
        f"<td>{_h(item['evidence_id'])}</td>"
        f"<td>{_h(item['title'])}</td>"
        f"<td>{_h(item['source_tier'])}</td>"
        f"<td><a href=\"{_h(item['source_url'])}\">{_h(item['source_url'])}</a></td>"
        f"<td>{_h(item['published_date'])}</td>"
        f"<td>{_h(item.get('page_start', ''))}"
        f"{('–' + _h(item.get('page_end'))) if item.get('page_end') else ''}</td>"
        f"<td>{_h(item.get('original_value', ''))} {_h(item.get('unit', ''))}</td>"
        f"<td>{_h(item.get('basis', ''))}</td>"
        f"<td>{_h(item['review_status'])}</td>"
        f"<td>{_h(item.get('excerpt', ''))}</td>"
        "</tr>"
        for item in case["evidence"]
    )
    artifact_html = "".join(
        "<details>"
        f"<summary>{_h(item['title'])} · {_h(item['module'])} · "
        f"{_h(item['review_status'])}</summary>"
        f"<pre>{_json_html(item['payload'])}</pre>"
        "</details>"
        for item in case["artifacts"]
    )
    hypothesis_rows = "".join(
        "<tr>"
        f"<td>{_h(item['hypothesis_id'])}</td>"
        f"<td>推断</td><td>{_h(item['statement'])}</td>"
        f"<td>{_h(item['status'])}</td>"
        f"<td>{_h(item['review_status'])}</td>"
        "</tr>"
        for item in case["hypotheses"]
    )
    audit_rows = "".join(
        "<tr>"
        f"<td>{_h(item['at'])}</td>"
        f"<td>{_h(item.get('source_module', ''))}</td>"
        f"<td>{_h(item.get('patch_id', ''))}</td>"
        f"<td>{_h(item['message'])}</td>"
        "</tr>"
        for item in case["audit_log"]
    )
    controls = workpaper["responsible_ai_controls"]
    controls_html = "".join(
        f"<li><code>{_h(key)}</code>：{_h(value)}</li>"
        for key, value in controls.items()
    )
    next_action = brief["next_action"]
    html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_h(company['name'])} · 完整研究工作底稿</title>
<style>
body{{font:15px/1.6 system-ui,-apple-system,sans-serif;color:#14233b;background:#eef4fa;margin:0}}
main{{max-width:1180px;margin:28px auto;padding:28px;background:white;box-shadow:0 8px 32px #1c365522}}
h1,h2{{color:#153d7a}} .meta{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}
.card{{border:1px solid #d9e5f2;border-radius:10px;padding:14px;margin:12px 0}}
table{{border-collapse:collapse;width:100%;font-size:13px}} th,td{{border:1px solid #d9e5f2;padding:8px;text-align:left;vertical-align:top}}
th{{background:#eef5fc}} pre{{white-space:pre-wrap;word-break:break-word;background:#f5f8fc;padding:12px}}
.caution{{color:#8a5414;background:#fff7e8;padding:10px;border-left:4px solid #d9982d}}
small{{color:#60738d}} a{{color:#185fb3;word-break:break-all}} code{{color:#153d7a}}
@media(max-width:760px){{main{{margin:0;padding:16px}}.meta{{grid-template-columns:1fr}}table{{display:block;overflow-x:auto}}}}
</style></head><body><main>
<h1>完整研究工作底稿</h1>
<div class="meta">
<div class="card"><b>公司</b><br>{_h(company['name'])} · {_h(company['canonical_code'])}</div>
<div class="card"><b>案件</b><br>{_h(case['case_id'])} · revision {_h(case['revision'])}</div>
<div class="card"><b>研究范围</b><br>{_h(scope['mode'])} · 截止日 {_h(scope['as_of_date'] or '当前')} · 有效市场日 {_h(scope['effective_market_date'])}</div>
</div>
<p><small>导出时间 {_h(workpaper['exported_at'])} · 案件指纹 {_h(workpaper['source_case_sha256'])}</small></p>
<h2>首页五问</h2>
<div class="card"><b>1. 当前最值得核验的问题</b><p>{_h(brief['primary_question'])}</p></div>
<div class="card"><b>2. 已经有什么证据</b><p>{_h(brief['evidence']['summary'])}</p><small>{_refs_html(brief['evidence'])}</small></div>
<div class="card"><b>3. 哪些证据互相矛盾</b>{contradiction_html}</div>
<div class="card"><b>4. 还有什么未知</b>{unknown_html}</div>
<div class="card"><b>5. 下一步应该验证什么</b><p>{_h(next_action['action'])}</p><small>{_h(next_action['module'])} · {_h(next_action['reason'])}</small></div>
<h2>五项专题研究问题</h2>
<table><thead><tr><th>问题</th><th>状态</th><th>摘要</th><th>下一步</th><th>引用</th></tr></thead><tbody>{lane_rows}</tbody></table>
<h2>证据登记册</h2>
<table><thead><tr><th>ID</th><th>标题</th><th>来源层级</th><th>URL</th><th>日期</th><th>页码</th><th>原值/单位</th><th>口径</th><th>复核</th><th>原文摘录</th></tr></thead><tbody>{evidence_rows}</tbody></table>
<h2>分析产物（不自动等于事实）</h2>{artifact_html}
<h2>研究推断</h2>
<table><thead><tr><th>ID</th><th>分类</th><th>陈述</th><th>状态</th><th>复核</th></tr></thead><tbody>{hypothesis_rows}</tbody></table>
<h2>审计日志</h2>
<table><thead><tr><th>时间</th><th>模块</th><th>Patch</th><th>记录</th></tr></thead><tbody>{audit_rows}</tbody></table>
<h2>负责任 AI 与控制</h2><ul>{controls_html}</ul>
<p class="caution">本底稿用于组织、核验和追溯研究过程，不构成投资建议。人工复核责任不会因导出而终止。</p>
</main></body></html>"""
    if len(html.encode("utf-8")) > MAX_WORKPAPER_BYTES:
        raise ResearchCaseWorkpaperError(
            f"HTML研究底稿超过{MAX_WORKPAPER_BYTES}字节上限。"
        )
    return html
