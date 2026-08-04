from datetime import date

from src.china_stock import build_company_identity
from src.research_thesis_ledger import (
    build_thesis_ledger_report_html,
    matching_evidence_items,
    thesis_status_counts,
)


def _thesis(**overrides: object) -> dict[str, object]:
    result: dict[str, object] = {
        "topic": "财务与业绩",
        "status": "待核验",
        "hypothesis": "收入增长能够转化为现金流改善",
        "confirmation_criteria": "经营现金流增速不低于收入增速",
        "invalidation_criteria": "经营现金流连续下降",
        "updated_at": "2026-08-04T12:00:00+00:00",
    }
    result.update(overrides)
    return result


def test_matching_evidence_requires_same_topic_and_official_source() -> None:
    items = [
        {
            "title": "年度报告",
            "published_date": date(2026, 4, 1),
            "source_url": "https://static.cninfo.com.cn/report.pdf",
            "evidence_group": "财务与业绩",
        },
        {
            "title": "治理公告",
            "published_date": date(2026, 4, 2),
            "source_url": "https://www.sse.com.cn/report.pdf",
            "evidence_group": "治理与风险",
        },
        {
            "title": "伪造年度报告",
            "published_date": date(2026, 4, 3),
            "source_url": "https://example.com/report.pdf",
            "evidence_group": "财务与业绩",
        },
    ]

    matches = matching_evidence_items(_thesis(), items)

    assert [item["title"] for item in matches] == ["年度报告"]


def test_thesis_status_counts_ignores_unknown_values() -> None:
    counts = thesis_status_counts(
        [
            _thesis(status="待核验"),
            _thesis(status="待核验"),
            _thesis(status="出现反方证据"),
            _thesis(status="自动看多"),
        ]
    )

    assert counts == {
        "待核验": 2,
        "暂有证据支持": 0,
        "出现反方证据": 1,
        "已失效": 0,
    }


def test_ledger_export_escapes_text_and_keeps_only_official_links() -> None:
    company = build_company_identity("600519", "贵州茅台")
    report = build_thesis_ledger_report_html(
        company,
        [
            _thesis(
                hypothesis="<script>alert(1)</script>",
                evidence_title="伪造公告",
                evidence_url="https://example.com/fake.pdf",
                evidence_date="2026-08-04",
            )
        ],
        generated_on=date(2026, 8, 4),
    )

    assert "<script>alert(1)</script>" not in report
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in report
    assert "https://example.com/fake.pdf" not in report
    assert "本次状态未绑定官方证据" in report
    assert "系统只按主题匹配官方证据" in report
