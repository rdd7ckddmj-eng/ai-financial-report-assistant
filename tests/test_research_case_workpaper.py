from copy import deepcopy
import json

import pytest

from src.research_case import QUESTION_KEYS, apply_case_patch, new_research_case
import src.research_case_workpaper as workpaper_module
from src.research_case_workpaper import (
    ResearchCaseWorkpaperError,
    build_research_case_workpaper,
    render_research_case_workpaper_html,
    serialise_research_case_workpaper,
)


NOW = "2026-08-30T12:00:00+00:00"
EXPORTED_AT = "2026-08-31T09:30:00+00:00"


def _ready_case(
    *,
    contradictions: bool = True,
    hostile_text: bool = False,
) -> dict[str, object]:
    hostile = '<script>alert("x")</script>' if hostile_text else "已核验"
    company_name = "贵州<em>茅台</em>" if hostile_text else "贵州茅台"
    case = new_research_case(
        "case-600519",
        {
            "code": "600519",
            "canonical_code": "600519.SH",
            "name": company_name,
            "exchange": "SH",
            "exchange_name": "上海证券交易所",
        },
        mode="current",
        as_of_date=None,
        effective_market_date="2026-08-29",
        created_at=NOW,
    )
    evidence = [
        {
            "evidence_id": "ev-report-1",
            "source_module": "annual_report",
            "source_tier": "official_disclosure",
            "title": f"年度报告 {hostile}",
            "source_url": "https://static.cninfo.com.cn/finalpage/report.pdf",
            "published_date": "2026-04-01",
            "page_start": 88,
            "page_end": 89,
            "excerpt": f"经营现金流未同步改善 {hostile}",
            "original_value": "68,500,000",
            "unit": "元",
            "basis": "合并现金流量表",
            "review_status": "confirmed",
        },
        {
            "evidence_id": "ev-note-rejected",
            "source_module": "annual_report",
            "source_tier": "user_provided",
            "title": "未经采纳的二手笔记",
            "source_url": "https://example.com/note",
            "published_date": "2026-04-02",
            "review_status": "rejected",
        },
    ]
    artifact = {
        "artifact_id": "artifact-annual-1",
        "module": "annual_report",
        "title": f"年报质量核验 {hostile}",
        "generated_at": "2026-08-30T12:05:00+00:00",
        "payload": {
            "cash_conversion": 0.68,
            "note": hostile,
            "source_pdf_embedded": False,
        },
        "review_status": "confirmed",
    }
    contradiction_items = (
        [
            {
                "contradiction_id": "contra-1",
                "summary": "利润增长与现金回款走势不一致。",
                "artifact_ids": ["artifact-annual-1"],
                "evidence_ids": ["ev-report-1"],
            }
        ]
        if contradictions
        else []
    )
    question_updates = {
        key: {
            "status": "answered",
            "summary": f"{key}已经形成有边界的回答。",
            "next_action": "继续跟踪后续公开披露。",
            "artifact_ids": ["artifact-annual-1"],
            "evidence_ids": ["ev-report-1"],
        }
        for key in QUESTION_KEYS
    }
    patch = {
        "patch_id": "patch-ready-1",
        "case_id": case["case_id"],
        "base_revision": case["revision"],
        "canonical_code": case["company"]["canonical_code"],
        "mode": case["scope"]["mode"],
        "as_of_date": case["scope"]["as_of_date"],
        "emitted_at": "2026-08-30T12:05:00+00:00",
        "source_module": "annual_report",
        "artifact": artifact,
        "evidence": evidence,
        "case_brief_update": {
            "primary_question": "利润增长为何没有转化为同幅度现金回款？",
            "evidence": {
                "summary": "已核对年报页码及原文，现金转化弱于利润表现。",
                "artifact_ids": ["artifact-annual-1"],
                "evidence_ids": ["ev-report-1"],
            },
            "contradictions": contradiction_items,
            "unknowns": [
                {
                    "unknown_id": "unknown-1",
                    "summary": "信用政策变化的具体贡献仍未知。",
                }
            ],
            "next_action": {
                "module": "annual_report",
                "action": "核对期后回款与信用政策说明",
                "reason": "需要区分结算时点差与持续的回款质量风险。",
            },
        },
        "question_updates": question_updates,
        "hypothesis_upserts": [
            {
                "hypothesis_id": "hypothesis-1",
                "statement": "现金转化下降可能与信用政策变化有关。",
                "status": "暂有证据支持",
                "updated_at": "2026-08-30T12:05:00+00:00",
                "source_module": "annual_report",
                "review_status": "confirmed",
                "confirmation_criteria": "期后回款与信用期延长同时出现。",
                "invalidation_criteria": "回款差异完全来自短期结算时点。",
            }
        ],
        "tracking": {"evidence_checked_at": "2026-08-30T12:05:00+00:00"},
        "audit_message": "年报证据、假设和五项研究问题已完成人工复核。",
    }
    ready = apply_case_patch(case, patch)
    assert ready["readiness"] == "ready_to_export"
    return ready


def test_formal_export_gate_rejects_case_without_real_evidence() -> None:
    case = new_research_case(
        "case-draft",
        {
            "code": "600519",
            "canonical_code": "600519.SH",
            "name": "贵州茅台",
            "exchange": "SH",
        },
        mode="current",
        as_of_date=None,
        effective_market_date="2026-08-29",
        created_at=NOW,
    )

    with pytest.raises(ResearchCaseWorkpaperError, match="真实证据引用"):
        build_research_case_workpaper(case, exported_at=EXPORTED_AT)


def test_workpaper_preserves_complete_case_and_explicit_classifications() -> None:
    case = _ready_case()
    workpaper = build_research_case_workpaper(case, exported_at=EXPORTED_AT)

    assert workpaper["research_case"] == case
    assert workpaper["research_case"] is not case
    assert tuple(workpaper["research_case"]["questions"]) == QUESTION_KEYS
    assert set(workpaper["research_case"]["case_brief"]) == {
        "primary_question",
        "evidence",
        "contradictions",
        "unknowns",
        "next_action",
    }
    index = workpaper["epistemic_index"]
    assert index["facts"]["reviewed_evidence_ids"] == ["ev-report-1"]
    assert index["inferences"]["hypothesis_ids"] == ["hypothesis-1"]
    assert index["unknowns"]["unknown_ids"] == ["unknown-1"]
    assert index["contradictions"]["contradiction_ids"] == ["contra-1"]
    assert index["other_source_records"]["evidence_ids"] == [
        "ev-note-rejected"
    ]
    assert workpaper["responsible_ai_controls"][
        "formal_export_requires_cited_source_evidence"
    ] is True


def test_export_keeps_provenance_artifacts_hypotheses_and_audit() -> None:
    workpaper = build_research_case_workpaper(
        _ready_case(), exported_at=EXPORTED_AT
    )
    case = workpaper["research_case"]

    evidence = case["evidence"][0]
    assert evidence["source_url"].startswith("https://static.cninfo.com.cn/")
    assert evidence["published_date"] == "2026-04-01"
    assert (evidence["page_start"], evidence["page_end"]) == (88, 89)
    assert evidence["review_status"] == "confirmed"
    assert evidence["original_value"] == "68,500,000"
    assert evidence["unit"] == "元"
    assert evidence["basis"] == "合并现金流量表"
    assert case["artifacts"][0]["payload"]["cash_conversion"] == 0.68
    assert case["hypotheses"][0]["confirmation_criteria"]
    assert case["audit_log"][0]["patch_id"] == "patch-ready-1"
    assert case["tracking"]["evidence_checked_at"]
    assert workpaper["responsible_ai_controls"]["source_pdf_or_binary_embedded"] is False


def test_json_is_stable_bounded_and_has_no_binary_or_pdf_body() -> None:
    workpaper = build_research_case_workpaper(
        _ready_case(), exported_at=EXPORTED_AT
    )
    serialised = serialise_research_case_workpaper(workpaper)
    decoded = json.loads(serialised)

    assert decoded == workpaper
    assert len(serialised.encode("utf-8")) < 500 * 1024
    assert "JVBERi0" not in serialised
    assert serialise_research_case_workpaper(workpaper) == serialised


def test_integrity_check_rejects_case_tampering_after_build() -> None:
    workpaper = build_research_case_workpaper(
        _ready_case(), exported_at=EXPORTED_AT
    )
    tampered = deepcopy(workpaper)
    tampered["research_case"]["case_brief"]["primary_question"] = "被篡改"

    with pytest.raises(ResearchCaseWorkpaperError, match="指纹"):
        serialise_research_case_workpaper(tampered)


def test_safe_html_escapes_every_dynamic_value() -> None:
    workpaper = build_research_case_workpaper(
        _ready_case(hostile_text=True), exported_at=EXPORTED_AT
    )
    rendered = render_research_case_workpaper_html(workpaper)

    assert '<script>alert("x")</script>' not in rendered
    assert "<em>茅台</em>" not in rendered
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in rendered
    assert "贵州&lt;em&gt;茅台&lt;/em&gt;" in rendered
    assert "完整研究工作底稿" in rendered


def test_empty_contradictions_are_not_promoted_to_no_contradiction_claim() -> None:
    workpaper = build_research_case_workpaper(
        _ready_case(contradictions=False), exported_at=EXPORTED_AT
    )
    rendered = render_research_case_workpaper_html(workpaper)

    assert workpaper["research_case"]["case_brief"]["contradictions"] == []
    assert "尚未记录可引用的矛盾" in rendered
    assert "不代表证据已经一致" in rendered
    assert "没有矛盾" not in rendered


def test_json_and_html_enforce_output_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(workpaper_module, "MAX_WORKPAPER_BYTES", 100)

    with pytest.raises(ResearchCaseWorkpaperError, match="超过100字节"):
        build_research_case_workpaper(_ready_case(), exported_at=EXPORTED_AT)
