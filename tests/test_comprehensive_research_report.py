from datetime import date

from src.china_stock import build_company_identity
from src.comprehensive_research import build_comprehensive_research_brief
from src.comprehensive_research_report import (
    build_comprehensive_research_audit_payload,
    build_comprehensive_research_report_html,
)


def test_report_exports_coverage_trace_and_safety_boundary() -> None:
    brief = build_comprehensive_research_brief(
        build_company_identity("600519", "贵州茅台"),
        announcements=[],
        generated_on=date(2026, 8, 1),
    )

    html = build_comprehensive_research_report_html(brief)

    assert "FANGZHENG AI · COMPREHENSIVE RESEARCH AGENT" in html
    assert "贵州茅台｜600519.SH" in html
    assert "Agent 执行轨迹" in html
    assert "不构成投资建议" in html
    assert "证据覆盖率" in html


def test_report_escapes_dynamic_company_and_source_text() -> None:
    company = build_company_identity("600519", "<script>alert(1)</script>")
    brief = build_comprehensive_research_brief(
        company,
        announcements=[
            {
                "title": "<img src=x onerror=alert(1)>",
                "date": "2026-07-31",
                "url": "https://static.cninfo.com.cn/test.pdf",
            }
        ],
        generated_on=date(2026, 8, 1),
    )

    html = build_comprehensive_research_report_html(brief)

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<img src=x onerror=alert(1)>" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html


def test_report_includes_only_matching_safe_radar_context() -> None:
    brief = build_comprehensive_research_brief(
        build_company_identity("600519", "贵州茅台"),
        announcements=[],
        generated_on=date(2026, 8, 2),
    )
    context = {
        "canonical_code": "600519.SH",
        "scan_date": "2026-08-02",
        "market_date": "2026-07-31",
        "research_priority": "P1｜立即核查",
        "radar_status": "复合异动",
        "triggered_signals": ["涨停候选", "<script>明显放量</script>"],
        "research_reasons": ["市场端同时触发2项异动证据"],
        "disclosure_status": "已核验近45日公告 1 条",
        "latest_disclosure": {
            "title": "贵州茅台重大事项公告",
            "published_date": "2026-07-31",
            "category": "其他公告",
            "attention": "高",
            "source_url": "https://static.cninfo.com.cn/test.pdf",
        },
    }

    html = build_comprehensive_research_report_html(
        brief,
        radar_context=context,
    )

    assert "研究触发来源" in html
    assert "WATCHLIST RADAR HANDOFF" in html
    assert "P1｜立即核查" in html
    assert "贵州茅台重大事项公告" in html
    assert "https://static.cninfo.com.cn/test.pdf" in html
    assert "<script>明显放量</script>" not in html
    assert "&lt;script&gt;明显放量&lt;/script&gt;" in html
    assert "不参与财务计算、证据覆盖率或投资判断" in html

    mismatched = build_comprehensive_research_report_html(
        brief,
        radar_context={**context, "canonical_code": "300750.SZ"},
    )
    assert "研究触发来源" not in mismatched


def test_report_rejects_untrusted_radar_disclosure_link() -> None:
    brief = build_comprehensive_research_brief(
        build_company_identity("600519", "贵州茅台"),
        announcements=[],
        generated_on=date(2026, 8, 2),
    )
    context = {
        "canonical_code": "600519.SH",
        "latest_disclosure": {
            "title": "待核验公告",
            "source_url": "javascript:alert(1)",
        },
    }

    html = build_comprehensive_research_report_html(
        brief,
        radar_context=context,
    )

    assert "javascript:alert(1)" not in html
    assert "本项没有可展示的官方链接" in html


def test_audit_payload_preserves_trace_and_matching_radar_context() -> None:
    brief = build_comprehensive_research_brief(
        build_company_identity("600519", "贵州茅台"),
        announcements=[],
        generated_on=date(2026, 8, 2),
    )
    context = {
        "canonical_code": "600519.SH",
        "scan_date": "2026-08-02",
        "market_date": "2026-07-31",
        "research_priority": "P2｜重点核查",
        "radar_status": "单项异动",
        "triggered_signals": ["明显放量"],
        "research_reasons": ["市场端触发1项异动证据"],
        "disclosure_status": "已核验近45日公告 1 条",
        "latest_disclosure": {
            "title": "贵州茅台重大事项公告",
            "published_date": "2026-07-31",
            "category": "其他公告",
            "attention": "中",
            "source_url": "https://static.cninfo.com.cn/test.pdf",
        },
    }

    payload = build_comprehensive_research_audit_payload(
        brief,
        radar_context=context,
    )

    assert payload["schema_version"] == "1.0"
    assert payload["report_type"] == "wfz_comprehensive_research_audit"
    assert payload["company"]["canonical_code"] == "600519.SH"
    assert payload["coverage"]["lane_count"] == 5
    assert len(payload["agent_trace"]) == 6
    assert payload["research_trigger"]["research_priority"] == (
        "P2｜重点核查"
    )
    assert payload["research_trigger"]["latest_disclosure"][
        "source_url"
    ] == "https://static.cninfo.com.cn/test.pdf"
    assert len(payload["evidence_fingerprint"]["value"]) == 64
    assert "不是数字签名" in "".join(payload["audit_boundary"])


def test_audit_payload_rejects_mismatch_and_untrusted_links() -> None:
    brief = build_comprehensive_research_brief(
        build_company_identity("600519", "贵州茅台"),
        announcements=[],
        generated_on=date(2026, 8, 2),
    )
    malicious_context = {
        "canonical_code": "600519.SH",
        "latest_disclosure": {
            "title": "待核验公告",
            "source_url": "javascript:alert(1)",
        },
    }

    payload = build_comprehensive_research_audit_payload(
        brief,
        radar_context=malicious_context,
    )
    assert payload["research_trigger"]["latest_disclosure"][
        "source_url"
    ] is None

    mismatched = build_comprehensive_research_audit_payload(
        brief,
        radar_context={
            **malicious_context,
            "canonical_code": "300750.SZ",
        },
    )
    assert mismatched["research_trigger"] is None


def test_audit_fingerprint_changes_with_evidence_payload() -> None:
    brief = build_comprehensive_research_brief(
        build_company_identity("600519", "贵州茅台"),
        announcements=[],
        generated_on=date(2026, 8, 2),
    )

    original = build_comprehensive_research_audit_payload(brief)
    brief["limitations"] = [*brief["limitations"], "新增研究限制"]
    changed = build_comprehensive_research_audit_payload(brief)

    assert original["evidence_fingerprint"]["value"] != changed[
        "evidence_fingerprint"
    ]["value"]
