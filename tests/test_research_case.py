from copy import deepcopy

import pytest

from src.research_case import (
    MAX_ARTIFACT_PAYLOAD_BYTES,
    MAX_CASE_BYTES,
    MAX_STORE_BYTES,
    QUESTION_KEYS,
    ResearchCaseCapacityError,
    ResearchCaseConflictError,
    ResearchCaseValidationError,
    apply_case_patch,
    calculate_readiness,
    empty_research_case_store,
    new_research_case,
    reduce_research_case_store,
    validate_research_case,
    validate_research_case_store,
)


NOW = "2026-08-30T12:00:00+00:00"


def _company(code: str = "600519") -> dict[str, str]:
    return {
        "code": code,
        "canonical_code": f"{code}.SH",
        "name": "贵州茅台",
        "exchange": "SH",
        "exchange_name": "上海证券交易所",
    }


def _case(*, historical: bool = False) -> dict[str, object]:
    return new_research_case(
        "case-600519",
        _company(),
        mode="historical" if historical else "current",
        as_of_date="2025-12-31" if historical else None,
        effective_market_date="2025-12-31" if historical else "2026-08-29",
        created_at=NOW,
    )


def _artifact(
    artifact_id: str = "artifact-1",
    **overrides: object,
) -> dict[str, object]:
    result: dict[str, object] = {
        "artifact_id": artifact_id,
        "module": "annual_report",
        "title": "年报关键数字复核",
        "generated_at": "2026-08-30T12:05:00+00:00",
        "payload": {"revenue": 1_000_000},
        "review_status": "not_required",
    }
    result.update(overrides)
    return result


def _evidence(
    evidence_id: str = "evidence-1",
    **overrides: object,
) -> dict[str, object]:
    result: dict[str, object] = {
        "evidence_id": evidence_id,
        "source_module": "annual_report",
        "source_tier": "official_disclosure",
        "title": "年度报告现金流量表",
        "source_url": "https://static.cninfo.com.cn/report.pdf",
        "published_date": "2026-04-01",
        "page_start": 88,
        "page_end": 88,
        "excerpt": "经营活动产生的现金流量净额为已披露原值。",
        "review_status": "not_required",
    }
    result.update(overrides)
    return result


def _patch(
    case: dict[str, object],
    patch_id: str = "patch-1",
    **overrides: object,
) -> dict[str, object]:
    result: dict[str, object] = {
        "patch_id": patch_id,
        "case_id": case["case_id"],
        "base_revision": case["revision"],
        "canonical_code": case["company"]["canonical_code"],
        "mode": case["scope"]["mode"],
        "as_of_date": case["scope"]["as_of_date"],
        "emitted_at": "2026-08-30T12:05:00+00:00",
        "source_module": "annual_report",
        "artifact": _artifact(),
        "audit_message": "已提取年报并等待核验。",
    }
    result.update(overrides)
    return result


def _create_command(
    store: dict[str, object],
    *,
    command_id: str = "create-1",
    case_id: str = "case-600519",
) -> dict[str, object]:
    return {
        "command_id": command_id,
        "base_store_revision": store["store_revision"],
        "action": "create",
        "emitted_at": NOW,
        "case_id": case_id,
        "company": _company(),
        "mode": "current",
        "as_of_date": None,
        "effective_market_date": "2026-08-29",
    }


def test_new_case_has_fixed_schema_and_five_unstarted_questions() -> None:
    case = _case()

    validate_research_case(case)
    assert case["schema_version"] == "1.0"
    assert tuple(case["questions"]) == QUESTION_KEYS
    assert {item["status"] for item in case["questions"].values()} == {
        "not_started"
    }
    assert set(case["case_brief"]) == {
        "primary_question",
        "evidence",
        "contradictions",
        "unknowns",
        "next_action",
    }
    assert case["readiness"] == "draft"


def test_company_identity_must_match_code_and_exchange() -> None:
    company = _company()
    company["canonical_code"] = "600519.SZ"

    with pytest.raises(ResearchCaseValidationError, match="不匹配"):
        new_research_case(
            "bad-company",
            company,
            mode="current",
            as_of_date=None,
            effective_market_date="2026-08-29",
            created_at=NOW,
        )


def test_patch_is_atomic_idempotent_and_revision_checked() -> None:
    original = _case()
    patch = _patch(original)
    once = apply_case_patch(original, patch)
    replay = apply_case_patch(once, patch)

    assert original["artifacts"] == []
    assert once["revision"] == 1
    assert replay == once

    stale = _patch(once, "patch-stale", base_revision=0)
    with pytest.raises(ResearchCaseConflictError, match="过期"):
        apply_case_patch(once, stale)


def test_late_validation_failure_does_not_partially_apply_patch() -> None:
    case = _case(historical=True)
    before = deepcopy(case)
    patch = _patch(
        case,
        evidence=[
            {
                "evidence_id": "future-report",
                "source_module": "annual_report",
                "source_tier": "official_disclosure",
                "title": "2026年年度报告",
                "source_url": "https://static.cninfo.com.cn/future.pdf",
                "published_date": "2026-04-01",
                "review_status": "confirmed",
            }
        ],
    )

    with pytest.raises(ResearchCaseValidationError, match="截止日之后"):
        apply_case_patch(case, patch)

    assert case == before


@pytest.mark.parametrize(
    "payload, error",
    [
        ({"pdf": b"not-json"}, "标准JSON"),
        ({"ratio": float("nan")}, "NaN"),
        ({"text": "中" * (MAX_ARTIFACT_PAYLOAD_BYTES + 1)}, "20KB"),
    ],
)
def test_artifact_payload_rejects_unsafe_or_oversized_values(
    payload: object,
    error: str,
) -> None:
    case = _case()
    patch = _patch(case, artifact=_artifact(payload=payload))

    with pytest.raises(ValueError, match=error):
        apply_case_patch(case, patch)


def test_total_case_json_limit_rejects_patch_without_mutating_case() -> None:
    case = _case()
    for index in range(7):
        case = apply_case_patch(
            case,
            _patch(
                case,
                f"large-{index}",
                artifact=_artifact(
                    f"large-artifact-{index}",
                    payload={"text": "x" * 19_000},
                ),
            ),
        )
    before = deepcopy(case)

    with pytest.raises(ResearchCaseCapacityError, match=str(MAX_CASE_BYTES)):
        apply_case_patch(
            case,
            _patch(
                case,
                "large-overflow",
                artifact=_artifact(
                    "large-artifact-overflow",
                    payload={"text": "x" * 19_000},
                ),
            ),
        )
    assert case == before


def test_total_store_json_limit_rejects_five_near_limit_cases() -> None:
    large_case = _case()
    for index in range(7):
        large_case = apply_case_patch(
            large_case,
            _patch(
                large_case,
                f"store-large-{index}",
                artifact=_artifact(
                    f"store-large-artifact-{index}",
                    payload={"text": "x" * 19_900},
                ),
            ),
        )
    large_case["case_brief"] = {
        "primary_question": "q" * 1_000,
        "evidence": {
            "summary": "e" * 2_500,
            "artifact_ids": ["store-large-artifact-0"],
            "evidence_ids": [],
        },
        "contradictions": [],
        "unknowns": [],
        "next_action": {
            "module": "annual_report",
            "action": "a" * 1_000,
            "reason": "r" * 2_000,
        },
    }
    large_case["readiness"] = calculate_readiness(large_case)
    validate_research_case(large_case)

    cases = {}
    for index in range(5):
        case_id = f"case-{index}-" + "x" * 73
        candidate = deepcopy(large_case)
        candidate["case_id"] = case_id
        cases[case_id] = candidate
    store = {
        "schema_version": "1.0",
        "store_revision": 50,
        "active_case_id": next(iter(cases)),
        "cases": cases,
        "applied_command_ids": [
            f"{index:02d}" + "c" * 78 for index in range(50)
        ],
    }

    with pytest.raises(ResearchCaseCapacityError, match=str(MAX_STORE_BYTES)):
        validate_research_case_store(store)


def test_artifact_and_summary_cannot_replace_real_evidence_for_export() -> None:
    case = _case()
    lane_updates = {
        key: {
            "status": "answered",
            "summary": "已核验。",
            "next_action": "继续核验后续公开资料。",
            "artifact_ids": ["artifact-1"],
            "evidence_ids": [],
        }
        for key in QUESTION_KEYS
    }
    artifact_only = apply_case_patch(
        case,
        _patch(
            case,
            case_brief_update={
                "primary_question": "利润增长为何没有转化为现金回款？",
                "evidence": {
                    "summary": "年报显示利润增长，但现金回款没有同步改善。",
                    "artifact_ids": ["artifact-1"],
                    "evidence_ids": [],
                },
                "contradictions": [],
                "unknowns": [
                    {
                        "unknown_id": "unknown-1",
                        "summary": "尚未确认回款差异来自信用政策还是期后时点。",
                    }
                ],
                "next_action": {
                    "module": "historical_lens",
                    "action": "核验期后回款与当时可得信息",
                    "reason": "需要隔离前视信息后判断现金质量。",
                },
            },
            question_updates=lane_updates,
        ),
    )
    assert artifact_only["readiness"] == "in_progress"


def test_documented_blocked_lane_can_remain_visible_in_formal_export() -> None:
    case = _case()
    lane_updates = {
        key: {
            "status": "blocked" if key == "point_in_time" else "answered",
            "summary": "证据仍存在缺口。" if key == "point_in_time" else "已核验。",
            "next_action": "补充截止日证据。",
            "artifact_ids": ["artifact-1"],
            "evidence_ids": ["evidence-1"],
        }
        for key in QUESTION_KEYS
    }
    blocked = apply_case_patch(
        case,
        _patch(
            case,
            evidence=[_evidence()],
            case_brief_update={
                "primary_question": "利润增长为何没有转化为现金回款？",
                "evidence": {
                    "summary": "已核对年报原文，但历史截止日证据仍缺失。",
                    "artifact_ids": ["artifact-1"],
                    "evidence_ids": ["evidence-1"],
                },
                "next_action": {
                    "module": "historical_lens",
                    "action": "补充历史截止日证据",
                    "reason": "被阻塞的专题不能包装成完整研究底稿。",
                },
            },
            question_updates=lane_updates,
        ),
    )
    assert blocked["readiness"] == "ready_to_export"

    undocumented_gap = apply_case_patch(
        blocked,
        _patch(
            blocked,
            "patch-undocumented-block",
            question_updates={
                "point_in_time": {
                    "status": "blocked",
                    "summary": "",
                    "next_action": "",
                    "artifact_ids": ["artifact-1"],
                    "evidence_ids": ["evidence-1"],
                }
            },
        ),
    )
    assert undocumented_gap["readiness"] == "in_progress"


def test_all_blocked_lanes_cannot_be_packaged_as_complete_research() -> None:
    case = _case()
    lane_updates = {
        key: {
            "status": "blocked",
            "summary": "该专题仍有明确证据缺口。",
            "next_action": "补充并核验官方来源。",
            "artifact_ids": ["artifact-1"],
            "evidence_ids": ["evidence-1"],
        }
        for key in QUESTION_KEYS
    }
    all_blocked = apply_case_patch(
        case,
        _patch(
            case,
            evidence=[_evidence()],
            case_brief_update={
                "primary_question": "当前证据能否支持任何研究判断？",
                "evidence": {
                    "summary": "已取得一条来源证据，但五个专题均未推进。",
                    "artifact_ids": ["artifact-1"],
                    "evidence_ids": ["evidence-1"],
                },
                "next_action": {
                    "module": "annual_report",
                    "action": "至少推进一项专题研究",
                    "reason": "全阻塞案件不能被包装成完整研究底稿。",
                },
            },
            question_updates=lane_updates,
        ),
    )
    assert all_blocked["readiness"] == "in_progress"


def test_real_evidence_and_unblocked_lanes_open_export_after_review() -> None:
    case = _case()
    lane_updates = {
        key: {
            "status": "answered",
            "summary": "已核验。",
            "next_action": "继续跟踪后续公开资料。",
            "artifact_ids": ["artifact-1"],
            "evidence_ids": ["evidence-1"],
        }
        for key in QUESTION_KEYS
    }
    ready = apply_case_patch(
        case,
        _patch(
            case,
            evidence=[_evidence()],
            case_brief_update={
                "primary_question": "利润增长为何没有转化为现金回款？",
                "evidence": {
                    "summary": "年报原文证据显示现金回款没有同步改善。",
                    "artifact_ids": ["artifact-1"],
                    "evidence_ids": ["evidence-1"],
                },
                "next_action": {
                    "module": "historical_lens",
                    "action": "继续核验期后回款",
                    "reason": "需要区分结算时点差与持续回款风险。",
                },
            },
            question_updates=lane_updates,
        ),
    )
    assert ready["readiness"] == "ready_to_export"

    pending = apply_case_patch(
        ready,
        _patch(
            ready,
            "patch-review",
            artifact=_artifact(review_status="pending"),
        ),
    )
    assert pending["readiness"] == "needs_human_review"


def test_complete_brief_alone_does_not_skip_unstarted_research_lanes() -> None:
    case = _case()
    patched = apply_case_patch(
        case,
        _patch(
            case,
            case_brief_update={
                "primary_question": "当前最值得核验的问题",
                "evidence": {
                    "summary": "已有一份年报产物。",
                    "artifact_ids": ["artifact-1"],
                    "evidence_ids": [],
                },
                "next_action": {
                    "module": "annual_report",
                    "action": "核对原文",
                    "reason": "专题泳道仍未完成。",
                },
            },
        ),
    )

    assert patched["readiness"] == "in_progress"


def test_brief_and_question_dangling_references_are_atomic_failures() -> None:
    case = _case()
    before = deepcopy(case)
    patch = _patch(
        case,
        case_brief_update={
            "evidence": {
                "summary": "引用了一份不存在的工作产物。",
                "artifact_ids": ["missing-artifact"],
                "evidence_ids": [],
            }
        },
        question_updates={
            "financial_quality": {
                "status": "in_progress",
                "artifact_ids": ["artifact-1"],
                "evidence_ids": ["missing-evidence"],
            }
        },
    )

    with pytest.raises(ResearchCaseValidationError, match="悬空引用"):
        apply_case_patch(case, patch)
    assert case == before


def test_patch_can_reference_artifact_and_evidence_created_atomically() -> None:
    case = _case()
    patched = apply_case_patch(
        case,
        _patch(
            case,
            evidence=[
                {
                    "evidence_id": "report-page-88",
                    "source_module": "annual_report",
                    "source_tier": "official_disclosure",
                    "title": "2025年年度报告第88页",
                    "source_url": "https://static.cninfo.com.cn/report.pdf",
                    "published_date": "2026-04-01",
                    "review_status": "corrected",
                    "page_start": 88,
                    "page_end": 89,
                    "excerpt": "经营活动现金流量净额下降。",
                    "original_value": "1,234.50",
                    "unit": "百万元",
                    "basis": "合并口径，报告期末。",
                }
            ],
            case_brief_update={
                "evidence": {
                    "summary": "已核对年报原文与单位口径。",
                    "artifact_ids": ["artifact-1"],
                    "evidence_ids": ["report-page-88"],
                }
            },
            question_updates={
                "financial_quality": {
                    "status": "answered",
                    "summary": "现金流与利润背离。",
                    "artifact_ids": ["artifact-1"],
                    "evidence_ids": ["report-page-88"],
                }
            },
        ),
    )

    assert patched["case_brief"]["evidence"]["evidence_ids"] == [
        "report-page-88"
    ]
    assert patched["evidence"][0]["review_status"] == "corrected"


@pytest.mark.parametrize(
    "source_tier,url,allowed",
    [
        ("public_market_data", "https://quote.eastmoney.com/sh600519.html", True),
        ("user_provided", "https://example.com/research-note", True),
        ("user_provided", "ftp://example.com/research-note", False),
        ("official_disclosure", "https://example.com/fake.pdf", False),
    ],
)
def test_evidence_source_tiers_enforce_http_and_domain_whitelists(
    source_tier: str,
    url: str,
    allowed: bool,
) -> None:
    case = _case()
    patch = _patch(
        case,
        evidence=[
            {
                "evidence_id": "source-1",
                "source_module": "annual_report",
                "source_tier": source_tier,
                "title": "公开来源",
                "source_url": url,
                "published_date": "2026-08-01",
                "review_status": "confirmed",
            }
        ],
    )

    if allowed:
        assert apply_case_patch(case, patch)["evidence"][0]["source_url"] == url
    else:
        with pytest.raises(ResearchCaseValidationError, match="source_tier"):
            apply_case_patch(case, patch)


def test_official_company_source_must_match_company_domain_allowlist() -> None:
    company = _company()
    company["official_domains"] = ["moutaichina.com"]
    case = new_research_case(
        "case-company-source",
        company,
        mode="current",
        as_of_date=None,
        effective_market_date="2026-08-29",
        created_at=NOW,
    )
    accepted = _patch(
        case,
        evidence=[
            {
                "evidence_id": "company-release",
                "source_module": "annual_report",
                "source_tier": "official_company",
                "title": "公司官网公开材料",
                "source_url": "https://www.moutaichina.com/release.pdf",
                "published_date": "2026-08-01",
                "review_status": "confirmed",
            }
        ],
    )

    assert apply_case_patch(case, accepted)["evidence"][0]["source_tier"] == (
        "official_company"
    )


def test_legacy_approved_review_status_is_not_accepted_in_v1() -> None:
    case = _case()

    with pytest.raises(ResearchCaseValidationError, match="review_status"):
        apply_case_patch(
            case,
            _patch(case, artifact=_artifact(review_status="approved")),
        )


def test_store_reducer_handles_create_replay_patch_and_conflict() -> None:
    store = empty_research_case_store()
    command = _create_command(store)
    created = reduce_research_case_store(store, command)
    replay = reduce_research_case_store(created, command)

    assert replay == created
    assert created["active_case_id"] == "case-600519"
    assert created["store_revision"] == 1

    case = created["cases"]["case-600519"]
    patched = reduce_research_case_store(
        created,
        {
            "command_id": "apply-1",
            "base_store_revision": 1,
            "action": "apply_patch",
            "emitted_at": "2026-08-30T12:05:00+00:00",
            "patch": _patch(case),
        },
    )
    assert patched["cases"]["case-600519"]["revision"] == 1

    with pytest.raises(ResearchCaseConflictError, match="store_revision"):
        reduce_research_case_store(
            patched,
            {
                **_create_command(patched, command_id="stale", case_id="other"),
                "base_store_revision": 1,
            },
        )


def test_store_never_silently_evicts_a_sixth_case() -> None:
    store = empty_research_case_store()
    for index in range(5):
        command = _create_command(
            store,
            command_id=f"create-{index}",
            case_id=f"case-{index}",
        )
        store = reduce_research_case_store(store, command)

    before = deepcopy(store)
    with pytest.raises(ResearchCaseCapacityError, match="容量5"):
        reduce_research_case_store(
            store,
            _create_command(store, command_id="create-six", case_id="case-6"),
        )
    assert store == before


def test_store_requires_archive_before_delete_and_clears_active_case() -> None:
    empty = empty_research_case_store()
    store = reduce_research_case_store(empty, _create_command(empty))
    with pytest.raises(ResearchCaseValidationError, match="只有已归档"):
        reduce_research_case_store(
            store,
            {
                "command_id": "delete-active",
                "base_store_revision": 1,
                "action": "delete_archived",
                "emitted_at": "2026-08-30T12:10:00+00:00",
                "case_id": "case-600519",
            },
        )

    archived = reduce_research_case_store(
        store,
        {
            "command_id": "archive-1",
            "base_store_revision": 1,
            "action": "archive",
            "emitted_at": "2026-08-30T12:11:00+00:00",
            "case_id": "case-600519",
        },
    )
    assert archived["active_case_id"] is None
    assert archived["cases"]["case-600519"]["lifecycle"] == "archived"

    archived_case = archived["cases"]["case-600519"]
    with pytest.raises(ResearchCaseValidationError, match="归档案件"):
        apply_case_patch(archived_case, _patch(archived_case, "after-archive"))
    with pytest.raises(ResearchCaseValidationError, match="不能重新激活"):
        reduce_research_case_store(
            archived,
            {
                "command_id": "activate-archived",
                "base_store_revision": 2,
                "action": "activate",
                "emitted_at": "2026-08-30T12:11:30+00:00",
                "case_id": "case-600519",
            },
        )
    with pytest.raises(ResearchCaseValidationError, match="roll_forward"):
        reduce_research_case_store(
            archived,
            {
                "command_id": "roll-archived",
                "base_store_revision": 2,
                "action": "roll_forward",
                "emitted_at": "2026-08-30T12:11:40+00:00",
                "case_id": "case-600519",
                "effective_market_date": "2026-08-30",
            },
        )

    deleted = reduce_research_case_store(
        archived,
        {
            "command_id": "delete-archived",
            "base_store_revision": 2,
            "action": "delete_archived",
            "emitted_at": "2026-08-30T12:12:00+00:00",
            "case_id": "case-600519",
        },
    )
    assert deleted["cases"] == {}


def test_patch_and_store_idempotence_windows_rotate_without_locking() -> None:
    case = _case()
    first_patch = _patch(
        case,
        "patch-window-0",
        artifact=_artifact("window-artifact"),
    )
    case = apply_case_patch(case, first_patch)
    for index in range(1, 52):
        case = apply_case_patch(
            case,
            _patch(
                case,
                f"patch-window-{index}",
                artifact=_artifact(
                    "window-artifact",
                    payload={"revision": index},
                ),
            ),
        )
    assert len(case["applied_patch_ids"]) == 50
    assert case["applied_patch_ids"][-1] == "patch-window-51"
    assert "patch-window-0" not in case["applied_patch_ids"]
    with pytest.raises(ResearchCaseConflictError, match="过期"):
        apply_case_patch(case, first_patch)

    empty = empty_research_case_store()
    first_command = _create_command(empty)
    store = reduce_research_case_store(empty, first_command)
    for index in range(55):
        store = reduce_research_case_store(
            store,
            {
                "command_id": f"activate-window-{index}",
                "base_store_revision": store["store_revision"],
                "action": "activate",
                "emitted_at": "2026-08-30T12:20:00+00:00",
                "case_id": "case-600519",
            },
        )
    assert len(store["applied_command_ids"]) == 50
    assert store["applied_command_ids"][-1] == "activate-window-54"
    assert first_command["command_id"] not in store["applied_command_ids"]
    with pytest.raises(ResearchCaseConflictError, match="store_revision"):
        reduce_research_case_store(store, first_command)


def test_current_rolls_only_forward_and_historical_never_rolls() -> None:
    store = reduce_research_case_store(
        empty_research_case_store(),
        _create_command(empty_research_case_store()),
    )
    rolled = reduce_research_case_store(
        store,
        {
            "command_id": "roll-1",
            "base_store_revision": 1,
            "action": "roll_forward",
            "emitted_at": "2026-08-31T12:00:00+00:00",
            "case_id": "case-600519",
            "effective_market_date": "2026-08-30",
        },
    )
    assert (
        rolled["cases"]["case-600519"]["scope"]["effective_market_date"]
        == "2026-08-30"
    )
    with pytest.raises(ResearchCaseValidationError, match="只能向后"):
        reduce_research_case_store(
            rolled,
            {
                "command_id": "roll-back",
                "base_store_revision": 2,
                "action": "roll_forward",
                "emitted_at": "2026-08-31T12:01:00+00:00",
                "case_id": "case-600519",
                "effective_market_date": "2026-08-29",
            },
        )
