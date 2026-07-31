"""Audited industry labels and conservative research peer-group rules.

The annual-report label is source evidence.  ``peer_group_*`` is a narrower
research tag created by this product, not an official regulatory conclusion.
At least two verified companies must share one tag before the UI may call the
selection a peer-group candidate.
"""

from __future__ import annotations

import csv
import re
from collections import Counter
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import TypedDict
from urllib.parse import urlparse

from src.financial_history import FinancialHistoryCase


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPANY_INDUSTRY_CATALOG_PATH = (
    PROJECT_ROOT / "data" / "verified" / "company_industry_catalog.csv"
)
ALLOWED_INDUSTRY_SOURCE_HOSTS = {
    "disc.static.szse.cn",
    "static.cninfo.com.cn",
    "dataclouds.cninfo.com.cn",
    "www.sse.com.cn",
    "static.sse.com.cn",
}
INDUSTRY_REQUIRED_FIELDS = {
    "company_code",
    "company_name",
    "exchange",
    "classification_basis",
    "disclosed_industry",
    "peer_group_code",
    "peer_group_name",
    "source_title",
    "source_url",
    "source_page",
    "reviewed_on",
    "evidence_grade",
    "notes",
}


class CompanyIndustryProfile(TypedDict):
    """One company classification with page-level source provenance."""

    company_code: str
    company_name: str
    exchange: str
    classification_basis: str
    disclosed_industry: str
    peer_group_code: str
    peer_group_name: str
    source_title: str
    source_url: str
    source_page: int
    reviewed_on: date
    evidence_grade: str
    notes: str


class PeerGroupCoverage(TypedDict):
    """Current audited-company coverage for one research peer tag."""

    peer_group_code: str
    peer_group_name: str
    company_count: int
    company_names: list[str]
    companies_needed: int
    ready: bool


class IndustryCatalogAudit(TypedDict):
    """Proof that industry evidence covers every audited company exactly once."""

    profile_count: int
    all_checks_passed: bool
    profiles: list[CompanyIndustryProfile]
    coverage: list[PeerGroupCoverage]


class PeerGroupAssessment(TypedDict):
    """Conservative scope decision for one selected company set."""

    company_count: int
    industry_group_count: int
    is_same_peer_group: bool
    scope_label: str
    group_names: list[str]
    limitation: str


def _required_text(row: dict[str, str], field_name: str) -> str:
    """Reject empty classification evidence instead of inventing a label."""
    value = str(row[field_name]).strip()
    if not value:
        raise ValueError(f"行业目录中的 {field_name} 不能为空。")
    return value


def _validate_profile(row: dict[str, str]) -> CompanyIndustryProfile:
    """Validate one source-controlled company classification row."""
    company_code = _required_text(row, "company_code")
    company_name = _required_text(row, "company_name")
    if not re.fullmatch(r"\d{6}", company_code):
        raise ValueError("行业目录中的股票代码必须是6位数字。")

    peer_group_code = _required_text(row, "peer_group_code")
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,63}", peer_group_code):
        raise ValueError("研究同行组代码必须使用小写英文和下划线。")

    exchange = _required_text(row, "exchange").upper()
    if exchange not in {"SH", "SZ", "BJ"}:
        raise ValueError("行业目录中的交易所必须是 SH、SZ 或 BJ。")

    source_url = _required_text(row, "source_url")
    parsed_url = urlparse(source_url)
    if (
        parsed_url.scheme != "https"
        or parsed_url.hostname not in ALLOWED_INDUSTRY_SOURCE_HOSTS
        or not parsed_url.path.lower().endswith(".pdf")
    ):
        raise ValueError("行业来源必须是受信任披露域名上的 HTTPS PDF。")

    try:
        source_page = int(str(row["source_page"]).strip())
    except ValueError as error:
        raise ValueError("行业来源页码必须是有效整数。") from error
    if source_page <= 0:
        raise ValueError("行业来源页码必须大于零。")

    try:
        reviewed_on = date.fromisoformat(
            _required_text(row, "reviewed_on")[:10]
        )
    except ValueError as error:
        raise ValueError("行业核验日期必须是有效 ISO 日期。") from error

    evidence_grade = _required_text(row, "evidence_grade")
    if evidence_grade != "A":
        raise ValueError("只有 A 级年报行业证据可以进入同行组目录。")

    return {
        "company_code": company_code,
        "company_name": company_name,
        "exchange": exchange,
        "classification_basis": _required_text(
            row,
            "classification_basis",
        ),
        "disclosed_industry": _required_text(row, "disclosed_industry"),
        "peer_group_code": peer_group_code,
        "peer_group_name": _required_text(row, "peer_group_name"),
        "source_title": _required_text(row, "source_title"),
        "source_url": source_url,
        "source_page": source_page,
        "reviewed_on": reviewed_on,
        "evidence_grade": evidence_grade,
        "notes": _required_text(row, "notes"),
    }


def load_company_industry_catalog(
    path: Path = COMPANY_INDUSTRY_CATALOG_PATH,
) -> list[CompanyIndustryProfile]:
    """Read and validate the audited industry evidence catalogue."""
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            missing = INDUSTRY_REQUIRED_FIELDS - set(reader.fieldnames or [])
            if missing:
                raise ValueError(
                    "行业目录缺少字段：" + "、".join(sorted(missing))
                )
            rows = list(reader)
    except OSError as error:
        raise ValueError("无法读取公司行业证据目录。") from error

    if not rows:
        raise ValueError("公司行业证据目录为空。")
    profiles = [_validate_profile(row) for row in rows]
    codes = [profile["company_code"] for profile in profiles]
    if len(codes) != len(set(codes)):
        raise ValueError("公司行业证据目录存在重复股票代码。")
    return profiles


def build_peer_group_coverage(
    profiles: Sequence[CompanyIndustryProfile],
) -> list[PeerGroupCoverage]:
    """Count verified companies without pretending one company is a peer set."""
    group_counts = Counter(
        profile["peer_group_code"] for profile in profiles
    )
    group_names = {
        profile["peer_group_code"]: profile["peer_group_name"]
        for profile in profiles
    }
    return [
        {
            "peer_group_code": group_code,
            "peer_group_name": group_names[group_code],
            "company_count": group_counts[group_code],
            "company_names": sorted(
                profile["company_name"]
                for profile in profiles
                if profile["peer_group_code"] == group_code
            ),
            "companies_needed": max(0, 2 - group_counts[group_code]),
            "ready": group_counts[group_code] >= 2,
        }
        for group_code in sorted(
            group_counts,
            key=lambda code: group_names[code],
        )
    ]


def audit_company_industry_catalog(
    cases: Sequence[FinancialHistoryCase],
    profiles: Sequence[CompanyIndustryProfile] | None = None,
) -> IndustryCatalogAudit:
    """Require exact identity coverage for the audited financial catalogue."""
    checked_profiles = list(
        profiles if profiles is not None else load_company_industry_catalog()
    )
    cases_by_code = {case["company_code"]: case for case in cases}
    profiles_by_code = {
        profile["company_code"]: profile for profile in checked_profiles
    }
    if len(cases_by_code) != len(cases):
        raise ValueError("财务接入清单存在重复股票代码。")
    if set(cases_by_code) != set(profiles_by_code):
        missing = sorted(set(cases_by_code) - set(profiles_by_code))
        extra = sorted(set(profiles_by_code) - set(cases_by_code))
        detail = []
        if missing:
            detail.append("缺少 " + "、".join(missing))
        if extra:
            detail.append("多出 " + "、".join(extra))
        raise ValueError("行业证据没有完整覆盖财务目录：" + "；".join(detail))
    for code, case in cases_by_code.items():
        if profiles_by_code[code]["company_name"] != case["company_name"]:
            raise ValueError("行业证据中的公司名称与财务目录不一致。")
        if profiles_by_code[code]["exchange"] != case["exchange"]:
            raise ValueError("行业证据中的交易所与财务目录不一致。")

    return {
        "profile_count": len(checked_profiles),
        "all_checks_passed": True,
        "profiles": checked_profiles,
        "coverage": build_peer_group_coverage(checked_profiles),
    }


def assess_peer_group(
    cases: Sequence[FinancialHistoryCase],
    profiles: Sequence[CompanyIndustryProfile],
) -> PeerGroupAssessment:
    """Decide whether the selection is a peer candidate or cross-industry."""
    checked_cases = list(cases)
    if len(checked_cases) < 2:
        raise ValueError("同行组判断至少需要两家公司。")
    codes = [case["company_code"] for case in checked_cases]
    if len(codes) != len(set(codes)):
        raise ValueError("同行组判断不能重复选择同一家公司。")

    profiles_by_code = {profile["company_code"]: profile for profile in profiles}
    if any(code not in profiles_by_code for code in codes):
        raise ValueError("所选公司缺少已核验的行业证据。")
    selected_profiles = [profiles_by_code[code] for code in codes]
    group_codes = {profile["peer_group_code"] for profile in selected_profiles}
    group_names = sorted(
        {profile["peer_group_name"] for profile in selected_profiles}
    )
    same_group = len(group_codes) == 1

    if same_group:
        scope_label = f"同行组候选｜{group_names[0]}"
        limitation = (
            "所选公司共享同一研究同行标签，但仍需检查业务分部占比、"
            "会计政策和异常事项后，才能用于估值比较。同行标签本身不"
            "代表公司质量排序，也不构成买卖建议。"
        )
    else:
        scope_label = f"跨行业比较（{len(group_codes)}个研究组）"
        limitation = (
            "所选公司分属不同研究同行组，只能进行跨行业结构展示。"
            "规模、利润率、现金转换和负债结构不可直接合成为优劣分数；"
            "本结果不含估值、预测或买卖建议。"
        )

    return {
        "company_count": len(checked_cases),
        "industry_group_count": len(group_codes),
        "is_same_peer_group": same_group,
        "scope_label": scope_label,
        "group_names": group_names,
        "limitation": limitation,
    }
