from pathlib import Path

import pytest

from src.flagship_cases import load_moutai_flagship_events


def test_moutai_flagship_events_are_verified_and_ordered() -> None:
    events = load_moutai_flagship_events()

    assert len(events) >= 3
    assert [event["event_date"] for event in events] == sorted(
        event["event_date"] for event in events
    )
    assert all(event["company_code"] == "600519" for event in events)
    assert all(event["evidence_grade"] == "A" for event in events)
    assert all(
        event["verification_status"] == "verified" for event in events
    )
    assert all(event["source_url"].startswith("https://") for event in events)


def test_flagship_loader_rejects_untrusted_sources(tmp_path: Path) -> None:
    bad_data = tmp_path / "events.csv"
    bad_data.write_text(
        "company_code,company_name,event_id,event_date,published_date,"
        "title,category,source_url,evidence_grade,verification_status,"
        "why_important\n"
        "600519,贵州茅台,bad,2024-01-01,2024-01-01,测试,测试,"
        "https://example.com/item,A,verified,测试\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="允许的官方 HTTPS 来源"):
        load_moutai_flagship_events(bad_data)
