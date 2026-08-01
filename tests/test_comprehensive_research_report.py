from datetime import date

from src.china_stock import build_company_identity
from src.comprehensive_research import build_comprehensive_research_brief
from src.comprehensive_research_report import (
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
