from copy import deepcopy

import pytest

from src.company_industry import (
    assess_peer_group,
    audit_company_industry_catalog,
    load_company_industry_catalog,
)
from src.financial_history import load_financial_history_catalog


def test_industry_catalog_preserves_page_level_annual_report_evidence() -> None:
    profiles = load_company_industry_catalog()

    assert [profile["company_code"] for profile in profiles] == [
        "600519",
        "000858",
        "300750",
        "002594",
    ]
    assert all(profile["source_page"] > 0 for profile in profiles)
    assert all(profile["source_url"].startswith("https://") for profile in profiles)
    assert all(profile["evidence_grade"] == "A" for profile in profiles)
    assert [profile["exchange"] for profile in profiles] == [
        "SH",
        "SZ",
        "SZ",
        "SZ",
    ]
    catl = next(
        profile for profile in profiles
        if profile["company_code"] == "300750"
    )
    assert catl["disclosed_industry"] == "锂离子电池制造（C3841）"
    assert catl["source_page"] == 11


def test_industry_audit_exactly_covers_financial_catalog() -> None:
    cases = load_financial_history_catalog()

    audit = audit_company_industry_catalog(cases)

    assert audit["all_checks_passed"] is True
    assert audit["profile_count"] == 4
    baijiu = next(
        item for item in audit["coverage"]
        if item["peer_group_code"] == "baijiu"
    )
    assert baijiu["company_names"] == ["五粮液", "贵州茅台"]
    assert baijiu["company_count"] == 2
    assert baijiu["companies_needed"] == 0
    assert baijiu["ready"] is True
    assert sum(item["ready"] for item in audit["coverage"]) == 1


def test_default_selection_is_cross_industry_not_a_peer_group() -> None:
    cases = load_financial_history_catalog()
    profiles = load_company_industry_catalog()

    assessment = assess_peer_group(cases, profiles)

    assert assessment["industry_group_count"] == 3
    assert assessment["is_same_peer_group"] is False
    assert assessment["scope_label"] == "跨行业比较（3个研究组）"
    assert "不含估值、预测或买卖建议" in assessment["limitation"]


def test_same_research_tag_is_only_a_peer_group_candidate() -> None:
    cases = load_financial_history_catalog()
    profiles = load_company_industry_catalog()

    assessment = assess_peer_group(
        cases[:2],
        profiles,
    )

    assert assessment["industry_group_count"] == 1
    assert assessment["is_same_peer_group"] is True
    assert assessment["scope_label"] == "同行组候选｜白酒制造"
    assert "业务分部占比" in assessment["limitation"]


def test_industry_audit_rejects_missing_or_mismatched_identity() -> None:
    cases = load_financial_history_catalog()
    profiles = load_company_industry_catalog()

    with pytest.raises(ValueError, match="没有完整覆盖"):
        audit_company_industry_catalog(cases, profiles[:-1])

    mismatched = deepcopy(profiles)
    mismatched[0]["company_name"] = "错误公司"
    with pytest.raises(ValueError, match="公司名称"):
        audit_company_industry_catalog(cases, mismatched)

    mismatched_exchange = deepcopy(profiles)
    mismatched_exchange[0]["exchange"] = "SZ"
    with pytest.raises(ValueError, match="交易所"):
        audit_company_industry_catalog(cases, mismatched_exchange)
