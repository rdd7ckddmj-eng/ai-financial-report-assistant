from datetime import date

from src.china_stock import build_company_identity
from src.evidence_delta import (
    INITIAL_LOOKBACK_DAYS,
    MAX_DELTA_LOOKBACK_DAYS,
    build_evidence_delta_report_html,
    build_evidence_delta_review,
    build_evidence_window,
)


def _announcement(
    title: str,
    published_date: date,
    category: str,
    attention: str = "中",
    url: str = "https://static.cninfo.com.cn/finalpage/test.PDF",
) -> dict[str, object]:
    return {
        "title": title,
        "date": published_date,
        "url": url,
        "category": category,
        "attention": attention,
    }


def test_first_evidence_window_uses_a_bounded_thirty_day_baseline() -> None:
    window = build_evidence_window(None, as_of_date=date(2026, 8, 4))

    assert (window["end_date"] - window["start_date"]).days + 1 == (
        INITIAL_LOOKBACK_DAYS
    )
    assert window["mode"] == "首次基准"
    assert window["baseline_date"] is None


def test_old_checkpoint_is_explicitly_truncated_to_one_year() -> None:
    window = build_evidence_window(
        "2024-01-01T09:00:00+00:00",
        as_of_date=date(2026, 8, 4),
    )

    assert (window["end_date"] - window["start_date"]).days + 1 == (
        MAX_DELTA_LOOKBACK_DAYS
    )
    assert window["baseline_date"] == date(2024, 1, 1)
    assert window["truncated"] is True


def test_review_groups_deduplicates_and_rejects_unofficial_links() -> None:
    company = build_company_identity("600519", "贵州茅台")
    window = build_evidence_window(
        "2026-08-02T10:00:00+00:00",
        as_of_date=date(2026, 8, 4),
    )
    valid = _announcement(
        "2026年半年度报告",
        date(2026, 8, 3),
        "财务报告",
        "高",
    )
    review = build_evidence_delta_review(
        company,
        [
            valid,
            valid,
            _announcement(
                "董事会决议公告",
                date(2026, 8, 2),
                "公司治理",
            ),
            _announcement(
                "不可信摘要",
                date(2026, 8, 4),
                "其他公告",
                url="https://example.com/not-official",
            ),
        ],
        window=window,
        generated_on=date(2026, 8, 4),
    )

    assert review["total_count"] == 2
    assert review["high_attention_count"] == 1
    assert review["group_counts"]["财务与业绩"] == 1
    assert review["group_counts"]["治理与风险"] == 1
    assert review["items"][0]["delta_status"] == "新增"
    assert review["items"][1]["delta_status"] == "同日待复核"

    report = build_evidence_delta_report_html(review)
    assert "贵州茅台" in report
    assert "同日待复核" in report
    assert "https://example.com/not-official" not in report
