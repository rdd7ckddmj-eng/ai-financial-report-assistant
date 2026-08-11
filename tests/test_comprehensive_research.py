from datetime import date

import pytest

from src.china_stock import build_company_identity
from src.comprehensive_research import build_comprehensive_research_brief


def _market_metrics():
    return {
        "latest_close": 1321.0,
        "latest_date": "2026-07-31",
        "daily_change": 0.01,
        "return_20d": 0.08,
        "return_60d": 0.12,
        "return_250d": 0.18,
        "annualised_volatility": 0.21,
        "max_drawdown": -0.25,
        "observations": 320,
    }


def _market_activity():
    return {
        "latest_date": "2026-07-31",
        "daily_return": 0.101,
        "volume_ratio_20d": 2.4,
        "volume_signal": "明显放量",
        "volume_percentile_250d": 0.95,
        "volume_percentile_sessions": 250,
        "turnover": 0.04,
        "turnover_status": "已取得普通换手率",
        "turnover_percentile_250d": 0.93,
        "turnover_percentile_sessions": 250,
        "effective_turnover": None,
        "effective_turnover_status": "数据不足",
        "limit_up_reference": 0.10,
        "limit_up_status": "涨停候选",
        "limit_up_note": "测试",
    }


def _financial_history():
    points = []
    for year in (2024, 2025):
        points.append(
            {
                "company_code": "600519",
                "company_name": "贵州茅台",
                "period_year": year,
                "report_year": year,
                "published_date": date(year + 1, 4, 1),
                "report_title": f"贵州茅台{year}年年度报告",
                "source_url": (
                    "https://static.cninfo.com.cn/finalpage/"
                    f"{year + 1}-04-01/{year}.PDF"
                ),
                "revenue": 100.0,
                "net_profit": 50.0,
                "operating_cash_flow": 55.0,
                "total_assets": 200.0,
                "total_liabilities": 40.0,
                "summary_page": 8,
                "balance_sheet_page": 90,
                "evidence_grade": "A",
                "verification_status": "verified",
                "accounting_basis": "reported",
                "notes": "测试",
                "revenue_growth": None if year == 2024 else 0.1,
                "net_profit_growth": None if year == 2024 else 0.12,
                "operating_cash_flow_growth": None if year == 2024 else 0.08,
                "net_margin": 0.5,
                "net_margin_change": None,
                "cash_conversion": 1.1,
                "cash_conversion_change": None,
                "liabilities_to_assets": 0.2,
                "liabilities_to_assets_change": None,
            }
        )
    return {
        "as_of_date": "2026-08-01",
        "points": points,
        "available_vintage_count": 2,
        "future_vintage_count": 0,
        "restatement_count": 0,
    }


def _financial_snapshot(
    code: str = "601398",
    status: str = "ready_for_human_review",
):
    company = build_company_identity(code, "工商银行")
    metric_specs = (
        ("revenue", "营业收入", "利润表", 100, 120_000_000_000.0),
        ("net_profit", "净利润", "利润表", 100, 36_000_000_000.0),
        (
            "operating_cash_flow",
            "经营活动现金流量净额",
            "现金流量表",
            102,
            40_000_000_000.0,
        ),
        (
            "total_assets",
            "资产总额",
            "资产负债表",
            98,
            800_000_000_000.0,
        ),
        (
            "total_liabilities",
            "负债总额",
            "资产负债表",
            98,
            600_000_000_000.0,
        ),
    )
    return {
        "schema_version": "1.0",
        "generated_at": "2026-08-06T00:00:00+00:00",
        "status": status,
        "status_label": "自动检查完成，等待人工复核",
        "company": company,
        "report": {
            "report_year": 2025,
            "published_date": "2026-04-20",
            "title": "工商银行2025年年度报告",
            "source_url": "https://static.cninfo.com.cn/example.pdf",
            "page_count": 200,
        },
        "source_fingerprint_sha256": "a" * 64,
        "statement_checks": {
            "income_statement_reconciled": True,
            "balance_sheet_reconciled": True,
            "cash_flow_statement_reconciled": True,
        },
        "unit": "元",
        "unit_note": "测试",
        "metrics": [
            {
                "key": key,
                "label": label,
                "current_yuan": (
                    amount if status == "ready_for_human_review" else None
                ),
                "previous_yuan": amount * 0.9,
                "change_rate": 1 / 9,
                "statement": statement,
                "pages": {"start": page, "end": page + 1},
            }
            for key, label, statement, page, amount in metric_specs
        ],
        "ratios": {
            "net_profit_margin": 0.3,
            "operating_cash_conversion": 40 / 36,
            "liabilities_to_assets": 0.75,
        },
        "limitations": ["自动提取，等待人工复核。"],
    }


def test_complete_brief_combines_five_independent_evidence_lanes() -> None:
    company = build_company_identity("600519", "贵州茅台")
    annual_url = (
        "https://static.cninfo.com.cn/finalpage/"
        "2026-04-01/1234567890.PDF"
    )
    brief = build_comprehensive_research_brief(
        company,
        market_metrics=_market_metrics(),
        market_activity=_market_activity(),
        market_source="测试公开行情",
        turnover_source="测试普通换手率",
        announcements=[
            {
                "title": "贵州茅台2025年年度报告",
                "date": date(2026, 4, 1),
                "url": annual_url,
                "category": "财务报告",
                "attention": "高",
            }
        ],
        announcements_status="已核验",
        latest_annual_report={
            "title": "贵州茅台2025年年度报告",
            "date": date(2026, 4, 1),
            "url": annual_url,
        },
        financial_history=_financial_history(),
        generated_on=date(2026, 8, 1),
    )

    assert brief["coverage_ratio"] == pytest.approx(1)
    assert brief["coverage_label"] == "证据覆盖较完整"
    assert brief["verified_lane_count"] == 5
    assert brief["conclusion"]["primary_key"] == "market_limit_up"
    assert [lane["key"] for lane in brief["evidence_lanes"]] == [
        "identity",
        "market",
        "disclosures",
        "annual_report",
        "financial_history",
    ]
    assert any(
        finding["headline"] == "涨停候选、明显放量、普通换手率历史高位"
        for finding in brief["findings"]
    )
    assert brief["actions"][0]["page"] == "anomaly"
    assert len(brief["trace"]) == 6


def test_missing_sources_stay_unavailable_instead_of_becoming_zero() -> None:
    brief = build_comprehensive_research_brief(
        build_company_identity("601398", "工商银行"),
        announcements=None,
        announcements_status="官方公告源暂不可用",
        generated_on=date(2026, 8, 1),
        data_errors=["行情源暂不可用"],
    )

    assert brief["verified_lane_count"] == 1
    assert brief["unavailable_lane_count"] == 4
    assert brief["coverage_ratio"] == pytest.approx(0.2)
    assert brief["coverage_label"] == "证据不足，优先补充来源"
    assert brief["conclusion"]["primary_key"] == "evidence_gap"
    assert brief["findings"] == []
    assert any("行情源暂不可用" in item for item in brief["limitations"])


def test_untrusted_disclosure_link_is_not_exported_as_verified_evidence() -> None:
    brief = build_comprehensive_research_brief(
        build_company_identity("300750", "宁德时代"),
        announcements=[
            {
                "title": "非官方摘要",
                "date": "2026-07-31",
                "url": "https://example.com/summary",
            }
        ],
        latest_annual_report={
            "title": "来源待核验的报告",
            "date": "2026-07-31",
            "url": "https://example.com/report.pdf",
        },
        generated_on=date(2026, 8, 1),
    )

    disclosure_lane = next(
        lane for lane in brief["evidence_lanes"]
        if lane["key"] == "disclosures"
    )
    annual_lane = next(
        lane for lane in brief["evidence_lanes"]
        if lane["key"] == "annual_report"
    )
    assert disclosure_lane["source_url"] is None
    assert annual_lane["status"] == "partial"
    assert annual_lane["source_url"] is None


def test_same_company_snapshot_fills_financial_lane_as_partial_evidence() -> None:
    company = build_company_identity("601398", "工商银行")

    brief = build_comprehensive_research_brief(
        company,
        financial_snapshot=_financial_snapshot(),
        generated_on=date(2026, 8, 7),
    )

    financial_lane = next(
        lane
        for lane in brief["evidence_lanes"]
        if lane["key"] == "financial_history"
    )
    assert financial_lane["status"] == "partial"
    assert financial_lane["label"] == "单期财务快照（待复核）"
    assert financial_lane["as_of_date"] == "2026-04-20"
    assert financial_lane["source_url"] == (
        "https://static.cninfo.com.cn/example.pdf"
    )
    finding = next(
        item for item in brief["findings"] if item["category"] == "财务快照"
    )
    assert finding["status"] == "partial"
    assert "营业收入 ¥1,200.00亿元" in finding["statement"]
    assert "利润表第100–101页" in finding["basis"]
    assert any(
        action["page"] == "financial_snapshot"
        and action["label"] == "复核并更新财务快照"
        for action in brief["actions"]
    )


def test_verified_history_wins_over_an_automatic_snapshot() -> None:
    company = build_company_identity("600519", "贵州茅台")

    brief = build_comprehensive_research_brief(
        company,
        financial_history=_financial_history(),
        financial_snapshot=_financial_snapshot(code="600519"),
        generated_on=date(2026, 8, 7),
    )

    financial_lane = next(
        lane
        for lane in brief["evidence_lanes"]
        if lane["key"] == "financial_history"
    )
    assert financial_lane["status"] == "verified"
    assert financial_lane["label"] == "已核验财务历史"
    assert not any(
        item["category"] == "财务快照" for item in brief["findings"]
    )
    assert not any(
        "单期财务快照由程序" in item for item in brief["limitations"]
    )


def test_snapshot_that_needs_review_does_not_publish_amounts() -> None:
    company = build_company_identity("601398", "工商银行")

    brief = build_comprehensive_research_brief(
        company,
        financial_snapshot=_financial_snapshot(status="needs_review"),
        generated_on=date(2026, 8, 7),
    )

    financial_lane = next(
        lane
        for lane in brief["evidence_lanes"]
        if lane["key"] == "financial_history"
    )
    assert financial_lane["status"] == "partial"
    assert "暂不输出金额观察" in financial_lane["summary"]
    assert not any(
        item["category"] == "财务快照" for item in brief["findings"]
    )


def test_mismatched_or_untrusted_snapshot_is_not_reused() -> None:
    company = build_company_identity("601398", "工商银行")
    mismatched = _financial_snapshot(code="600519")
    unsafe = _financial_snapshot()
    unsafe["report"]["source_url"] = "https://example.com/report.pdf"

    for snapshot in (mismatched, unsafe):
        brief = build_comprehensive_research_brief(
            company,
            financial_snapshot=snapshot,
            generated_on=date(2026, 8, 7),
        )
        financial_lane = next(
            lane
            for lane in brief["evidence_lanes"]
            if lane["key"] == "financial_history"
        )
        assert financial_lane["status"] == "unavailable"
        assert not any(
            item["category"] == "财务快照" for item in brief["findings"]
        )
        assert any(
            action["page"] == "financial_snapshot"
            and action["label"] == "生成最新年报财务快照"
            for action in brief["actions"]
        )
