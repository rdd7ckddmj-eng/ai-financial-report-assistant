from copy import deepcopy
import json

import pytest

from src.research_case import (
    QUESTION_KEYS,
    ResearchCaseValidationError,
    apply_case_patch,
    new_research_case,
    validate_research_case,
)
from src.research_case_bridge import (
    COMPREHENSIVE_ARTIFACT_PAYLOAD_BYTES,
    build_comprehensive_research_case_patch,
)
from src.research_case_workpaper import build_research_case_workpaper


NOW = "2026-08-30T12:00:00+00:00"


def _company() -> dict[str, object]:
    return {
        "code": "600519",
        "canonical_code": "600519.SH",
        "name": "贵州茅台",
        "exchange": "SH",
        "exchange_name": "上海证券交易所",
        "official_domains": ["moutaichina.com"],
    }


def _case(*, historical: bool = False) -> dict[str, object]:
    return new_research_case(
        "case-600519",
        _company(),
        mode="historical" if historical else "current",
        as_of_date="2025-12-31" if historical else None,
        effective_market_date="2025-12-30" if historical else "2026-08-29",
        created_at=NOW,
    )


def _lane(
    key: str,
    *,
    status: str = "verified",
    source_url: str | None = None,
    as_of_date: str = "2026-08-29",
) -> dict[str, object]:
    return {
        "key": key,
        "label": f"{key}证据",
        "status": status,
        "summary": f"{key}已经形成一条可复核摘要。",
        "source": f"{key}公开来源",
        "as_of_date": as_of_date,
        "source_url": source_url,
        "limitation": "该摘要只描述已经取得的公开证据。",
    }


def _brief() -> dict[str, object]:
    return {
        "company": _company(),
        "generated_on": "2026-08-30",
        "coverage_ratio": 0.8,
        "coverage_label": "证据覆盖较完整",
        "verified_lane_count": 4,
        "partial_lane_count": 1,
        "unavailable_lane_count": 0,
        "conclusion": {
            "headline": "利润与现金回款节奏值得继续核验",
            "explanation": "现有公开证据支持安排下一步核验，但不构成投资建议。",
            "next_question": "利润变化是否已经转化为可持续现金回款？",
            "evidence_summary": "五条证据链中四条已核验、一条部分可用。",
            "primary_key": "cash_conversion",
            "pillars": [],
        },
        "evidence_lanes": [
            _lane("identity", source_url=None),
            _lane(
                "market",
                source_url="https://quote.eastmoney.com/sh600519.html",
            ),
            _lane(
                "disclosures",
                source_url="https://static.cninfo.com.cn/finalpage/notice.pdf",
            ),
            _lane(
                "annual_report",
                source_url="https://www.sse.com.cn/disclosure/report.pdf",
            ),
            _lane(
                "financial_history",
                status="partial",
                source_url="https://static.cninfo.com.cn/finalpage/annual.pdf",
            ),
        ],
        "findings": [{"full": "桥接层不应复制这组详细结果"}],
        "actions": [
            {
                "priority": 1,
                "page": "annual",
                "label": "进入年报与证据分析",
                "reason": "继续核对财务页码与口径。",
            }
        ],
        "trace": [{"full": "桥接层不应复制完整执行轨迹"}],
        "limitations": ["完整限制列表不写入紧凑artifact。"],
    }


def _patch(
    case: dict[str, object],
    brief: dict[str, object],
    *,
    patch_id: str = "bridge-1",
) -> dict[str, object]:
    return build_comprehensive_research_case_patch(
        case,
        brief,
        patch_id=patch_id,
        emitted_at=NOW,
    )


def test_bridge_maps_all_five_questions_and_returns_applicable_patch() -> None:
    case = _case()
    brief = _brief()
    case_before = deepcopy(case)
    brief_before = deepcopy(brief)
    patch = _patch(case, brief)

    assert tuple(patch["question_updates"]) == QUESTION_KEYS
    assert patch["source_module"] == "comprehensive_research"
    assert patch["canonical_code"] == "600519.SH"

    applied = apply_case_patch(case, patch)
    validate_research_case(applied)
    assert applied["revision"] == 1
    assert applied["questions"]["recent_events"]["status"] == "answered"
    assert applied["questions"]["financial_quality"]["status"] == "in_progress"
    assert case == case_before
    assert brief == brief_before


def test_source_derived_summaries_are_not_promoted_to_workpaper_facts() -> None:
    case = _case()
    patch = _patch(case, _brief())

    assert patch["evidence"]
    assert {
        item["review_status"] for item in patch["evidence"]
    } == {"not_required"}
    assert all(
        "不是官方原文摘录" in item["basis"]
        for item in patch["evidence"]
    )

    applied = apply_case_patch(case, patch)
    assert applied["readiness"] == "ready_to_export"
    workpaper = build_research_case_workpaper(applied, exported_at=NOW)
    evidence_ids = [item["evidence_id"] for item in patch["evidence"]]

    assert workpaper["epistemic_index"]["facts"]["reviewed_evidence_ids"] == []
    assert workpaper["epistemic_index"]["other_source_records"][
        "evidence_ids"
    ] == evidence_ids


def test_artifact_is_under_four_kb_and_does_not_copy_large_objects() -> None:
    class MustNotStringify:
        def __str__(self) -> str:
            raise AssertionError("arbitrary objects must not be stringified")

    brief = _brief()
    brief["raw_dataframe"] = MustNotStringify()
    brief["pdf_bytes"] = MustNotStringify()
    brief["chart"] = MustNotStringify()
    brief["trace"] = [MustNotStringify()]
    for lane in brief["evidence_lanes"]:
        lane["summary"] = "很长的摘要" * 2_000
        lane["raw_table"] = MustNotStringify()

    patch = _patch(_case(), brief)
    payload = patch["artifact"]["payload"]
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    assert len(encoded) <= COMPREHENSIVE_ARTIFACT_PAYLOAD_BYTES
    serialised = encoded.decode("utf-8")
    assert "raw_dataframe" not in serialised
    assert "pdf_bytes" not in serialised
    assert "chart" not in serialised
    assert "trace" not in serialised
    assert "findings" not in serialised


def test_missing_historical_cutoff_evidence_stays_blocked() -> None:
    patch = _patch(_case(), _brief())
    point_in_time = patch["question_updates"]["point_in_time"]

    assert point_in_time["status"] == "blocked"
    assert point_in_time["evidence_ids"] == []
    assert "Historical Lens" in point_in_time["next_action"]
    assert patch["case_brief_update"]["next_action"]["module"] == (
        "historical_lens"
    )


def test_explicit_pre_cutoff_historical_lane_can_answer_point_in_time() -> None:
    case = _case(historical=True)
    brief = _brief()
    for lane in brief["evidence_lanes"]:
        lane["as_of_date"] = "2025-12-30"
    brief["generated_on"] = "2025-12-31"
    brief["evidence_lanes"].append(
        _lane(
            "historical_lens",
            source_url="https://static.cninfo.com.cn/finalpage/cutoff.pdf",
            as_of_date="2025-12-30",
        )
    )

    patch = _patch(case, brief)
    point_in_time = patch["question_updates"]["point_in_time"]

    assert point_in_time["status"] == "answered"
    assert len(point_in_time["evidence_ids"]) == 1
    assert patch["case_brief_update"]["next_action"]["module"] == (
        "annual_report"
    )
    apply_case_patch(case, patch)


def test_post_cutoff_sources_are_not_written_into_historical_case() -> None:
    case = _case(historical=True)
    brief = _brief()
    brief["evidence_lanes"].append(
        _lane(
            "historical_lens",
            source_url="https://static.cninfo.com.cn/finalpage/future.pdf",
            as_of_date="2026-04-01",
        )
    )

    patch = _patch(case, brief)

    assert patch["evidence"] == []
    assert patch["question_updates"]["point_in_time"]["status"] == "blocked"
    apply_case_patch(case, patch)


def test_invalid_url_is_omitted_and_verified_lane_is_downgraded() -> None:
    brief = _brief()
    disclosures = next(
        lane
        for lane in brief["evidence_lanes"]
        if lane["key"] == "disclosures"
    )
    disclosures["source_url"] = "https://example.com/not-official.pdf"

    patch = _patch(_case(), brief)
    disclosure_evidence = [
        item
        for item in patch["evidence"]
        if "disclosures" in item["title"]
    ]

    assert disclosure_evidence == []
    assert patch["question_updates"]["recent_events"]["status"] == "in_progress"
    assert patch["question_updates"]["recent_events"]["evidence_ids"] == []
    apply_case_patch(_case(), patch)


def test_source_tiers_are_inferred_only_from_case_allowlists() -> None:
    brief = _brief()
    annual = next(
        lane
        for lane in brief["evidence_lanes"]
        if lane["key"] == "annual_report"
    )
    annual["source_url"] = "https://www.moutaichina.com/report.pdf"

    patch = _patch(_case(), brief)
    tiers_by_title = {
        item["title"].split("｜", 1)[0]: item["source_tier"]
        for item in patch["evidence"]
    }

    assert tiers_by_title["market证据"] == "public_market_data"
    assert tiers_by_title["disclosures证据"] == "official_disclosure"
    assert tiers_by_title["annual_report证据"] == "official_company"
    apply_case_patch(_case(), patch)


def test_empty_contradictions_are_not_rewritten_as_no_contradiction() -> None:
    brief = _brief()
    brief["contradictions"] = []

    patch = _patch(_case(), brief)

    assert "contradictions" not in patch["case_brief_update"]
    assert "无矛盾" not in json.dumps(patch, ensure_ascii=False)


def test_unknowns_are_stable_deduplicated_and_framed_as_open_work() -> None:
    case = _case()
    brief = _brief()
    financial = next(
        lane
        for lane in brief["evidence_lanes"]
        if lane["key"] == "financial_history"
    )
    financial["limitation"] = "财务口径仍待人工核验。"
    brief["limitations"] = [
        "财务口径仍待人工核验。",
        "财务口径仍待人工核验。",
        "公告覆盖范围仍需人工确认。",
    ]

    first = _patch(case, brief, patch_id="unknowns-first")
    second = _patch(case, brief, patch_id="unknowns-second")
    unknowns = first["case_brief_update"]["unknowns"]

    assert unknowns == second["case_brief_update"]["unknowns"]
    assert len(unknowns) == 2
    assert sum("财务口径仍待人工核验" in item["summary"] for item in unknowns) == 1
    assert all(
        item["summary"].startswith(("待核验", "待补充", "需人工覆盖检查"))
        for item in unknowns
    )
    assert len({item["unknown_id"] for item in unknowns}) == len(unknowns)


def test_unknowns_preserve_existing_items_and_bound_new_items() -> None:
    case = _case()
    case["case_brief"]["unknowns"] = [
        {
            "unknown_id": "human-unknown-1",
            "summary": "人工登记：经销渠道数据仍待取得。",
        }
    ]
    validate_research_case(case)
    brief = _brief()
    brief["limitations"] = [f"限制项{index}仍待核验。" for index in range(12)]
    for lane in brief["evidence_lanes"]:
        lane["status"] = "partial"
        lane["limitation"] = f"{lane['key']}证据边界仍待核验。"

    patch = _patch(case, brief)
    unknowns = patch["case_brief_update"]["unknowns"]

    assert unknowns[0]["unknown_id"] == "human-unknown-1"
    assert len(unknowns) == 7  # One existing item plus at most six new items.
    apply_case_patch(case, patch)


def test_no_extractable_unknown_writes_an_explicit_coverage_check() -> None:
    brief = _brief()
    brief["limitations"] = []
    for lane in brief["evidence_lanes"]:
        lane["status"] = "verified"
        lane["limitation"] = ""

    patch = _patch(_case(), brief)
    unknowns = patch["case_brief_update"]["unknowns"]

    assert len(unknowns) == 1
    assert "尚未完成未知项登记" in unknowns[0]["summary"]
    assert "人工覆盖检查" in unknowns[0]["summary"]
    assert "无未知" not in unknowns[0]["summary"]
    assert "没有未知" not in unknowns[0]["summary"]


def test_bridge_rejects_a_brief_for_another_company() -> None:
    brief = _brief()
    brief["company"] = {
        **_company(),
        "code": "000001",
        "canonical_code": "000001.SZ",
        "exchange": "SZ",
    }

    with pytest.raises(ResearchCaseValidationError, match="公司不匹配"):
        _patch(_case(), brief)
