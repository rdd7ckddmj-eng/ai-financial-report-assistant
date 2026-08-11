from src.research_conclusion import build_research_conclusion


def _lanes(
    *,
    market: str = "verified",
    disclosures: str = "verified",
    financial: str = "verified",
    financial_source: str = "逐页核验年度报告数据集",
):
    return [
        {"key": "identity", "status": "verified"},
        {"key": "market", "status": market},
        {"key": "disclosures", "status": disclosures},
        {"key": "annual_report", "status": "verified"},
        {
            "key": "financial_history",
            "status": financial,
            "source": financial_source,
        },
    ]


def _stable_financial_history():
    return {
        "points": [
            {
                "period_year": 2025,
                "revenue_growth": 0.08,
                "net_profit_growth": 0.10,
                "operating_cash_flow_growth": 0.06,
            }
        ]
    }


def test_low_coverage_makes_the_evidence_gap_the_primary_conclusion() -> None:
    conclusion = build_research_conclusion(
        coverage_ratio=0.2,
        evidence_lanes=_lanes(
            market="unavailable",
            disclosures="unavailable",
            financial="unavailable",
        ),
    )

    assert conclusion["primary_key"] == "evidence_gap"
    assert "当前证据不足" in conclusion["headline"]
    assert "2 条已核验" in conclusion["evidence_summary"]


def test_verified_cash_flow_mismatch_outranks_market_activity() -> None:
    history = _stable_financial_history()
    history["points"][0]["net_profit_growth"] = 0.12
    history["points"][0]["operating_cash_flow_growth"] = -0.08

    conclusion = build_research_conclusion(
        coverage_ratio=1.0,
        evidence_lanes=_lanes(),
        market_activity={
            "limit_up_status": "涨停候选",
            "volume_ratio_20d": 2.5,
            "turnover_percentile_250d": 0.95,
        },
        financial_history=history,
    )

    assert conclusion["primary_key"] == "financial_cash_mismatch"
    assert "利润增长但经营现金流下降" in conclusion["headline"]
    assert conclusion["pillars"][0]["state"] == "attention"


def test_limit_up_candidate_becomes_primary_without_financial_mismatch() -> None:
    conclusion = build_research_conclusion(
        coverage_ratio=1.0,
        evidence_lanes=_lanes(),
        market_activity={
            "limit_up_status": "涨停候选",
            "volume_ratio_20d": 1.2,
            "turnover_percentile_250d": 0.5,
        },
        financial_history=_stable_financial_history(),
    )

    assert conclusion["primary_key"] == "market_limit_up"
    assert "市场异动" in conclusion["headline"]


def test_high_attention_official_disclosure_is_ranked_for_reading() -> None:
    conclusion = build_research_conclusion(
        coverage_ratio=1.0,
        evidence_lanes=_lanes(),
        market_activity={
            "limit_up_status": "未触发",
            "volume_ratio_20d": 1.1,
            "turnover_percentile_250d": 0.4,
        },
        announcements=[
            {
                "title": "重大事项公告",
                "date": "2026-08-01",
                "attention": "高",
                "url": "https://static.cninfo.com.cn/test.pdf",
            }
        ],
        financial_history=_stable_financial_history(),
    )

    assert conclusion["primary_key"] == "disclosure_high_attention"
    assert "重大事项公告" in conclusion["headline"]
    assert "不代表公告内容属于利好或利空" in conclusion["explanation"]


def test_older_high_attention_disclosure_does_not_override_newer_item() -> None:
    conclusion = build_research_conclusion(
        coverage_ratio=1.0,
        evidence_lanes=_lanes(),
        announcements=[
            {
                "title": "年度报告",
                "date": "2026-04-01",
                "attention": "高",
                "url": "https://static.cninfo.com.cn/annual.pdf",
            },
            {
                "title": "一般事项公告",
                "date": "2026-08-01",
                "attention": "低",
                "url": "https://static.cninfo.com.cn/latest.pdf",
            },
        ],
        financial_history=_stable_financial_history(),
    )

    assert conclusion["primary_key"] == "no_rule_triggered"


def test_complete_evidence_without_trigger_returns_a_neutral_boundary() -> None:
    conclusion = build_research_conclusion(
        coverage_ratio=1.0,
        evidence_lanes=_lanes(),
        market_activity={
            "limit_up_status": "未触发",
            "volume_ratio_20d": 1.1,
            "turnover_percentile_250d": 0.4,
        },
        announcements=[],
        financial_history=_stable_financial_history(),
    )

    assert conclusion["primary_key"] == "no_rule_triggered"
    assert "不代表公司质量良好" in conclusion["explanation"]
    assert all(
        pillar["state"] == "clear" for pillar in conclusion["pillars"]
    )


def test_single_period_snapshot_mismatch_keeps_human_review_warning() -> None:
    snapshot = {
        "status": "ready_for_human_review",
        "metrics": [
            {"key": "revenue", "change_rate": 0.10},
            {"key": "net_profit", "change_rate": 0.12},
            {"key": "operating_cash_flow", "change_rate": -0.05},
        ],
    }
    conclusion = build_research_conclusion(
        coverage_ratio=0.7,
        evidence_lanes=_lanes(
            financial="partial",
            financial_source="最新完整年度报告自动提取候选",
        ),
        financial_snapshot=snapshot,
    )

    assert conclusion["primary_key"] == "snapshot_cash_mismatch"
    assert "需优先核对年报原文" in conclusion["headline"]
    assert "尚未经过人工逐页复核" in conclusion["explanation"]
