from src.browser_research_state import (
    MAX_EVIDENCE_CHECKPOINTS,
    MAX_LOCAL_WATCHLIST,
    MAX_RECENT_RESEARCH,
    MAX_RESEARCH_THESES,
    apply_browser_research_command,
    normalise_browser_research_state,
)


def _company(code: str, name: str = "测试公司") -> dict[str, str]:
    return {
        "code": code,
        "name": name,
        "exchange": "SH",
        "exchange_name": "上海证券交易所",
        "canonical_code": f"{code}.SH",
    }


def _command(
    action: str,
    code: str,
    command_id: str,
) -> dict[str, object]:
    return {
        "id": command_id,
        "action": action,
        "company": _company(code),
        "timestamp": "2026-08-02T03:15:00+00:00",
    }


def test_recent_research_is_deduplicated_promoted_and_bounded() -> None:
    state: object = {}
    for index in range(MAX_RECENT_RESEARCH + 2):
        code = f"60{index:04d}"
        state = apply_browser_research_command(
            state,
            _command("record_research", code, f"recent-{index}"),
        )

    state = apply_browser_research_command(
        state,
        _command("record_research", "600003", "recent-promote"),
    )

    assert len(state["recent"]) == MAX_RECENT_RESEARCH
    assert state["recent"][0]["canonical_code"] == "600003.SH"
    assert len({item["canonical_code"] for item in state["recent"]}) == (
        MAX_RECENT_RESEARCH
    )


def test_watchlist_toggle_adds_removes_and_stays_small() -> None:
    state: object = {}
    for index in range(MAX_LOCAL_WATCHLIST + 2):
        code = f"60{index:04d}"
        state = apply_browser_research_command(
            state,
            _command("toggle_watchlist", code, f"watch-{index}"),
        )

    assert len(state["watchlist"]) == MAX_LOCAL_WATCHLIST
    assert state["watchlist"][0]["canonical_code"] == "600006.SH"

    state = apply_browser_research_command(
        state,
        _command("toggle_watchlist", "600006", "watch-remove"),
    )
    assert all(
        item["canonical_code"] != "600006.SH"
        for item in state["watchlist"]
    )


def test_duplicate_command_is_idempotent() -> None:
    command = _command("toggle_watchlist", "600519", "same-command")
    once = apply_browser_research_command({}, command)
    twice = apply_browser_research_command(once, command)

    assert twice == once
    assert len(twice["watchlist"]) == 1


def test_evidence_checkpoint_is_replaced_and_bounded() -> None:
    state: object = {}
    for index in range(MAX_EVIDENCE_CHECKPOINTS + 2):
        code = f"60{index:04d}"
        state = apply_browser_research_command(
            state,
            _command(
                "save_evidence_checkpoint",
                code,
                f"checkpoint-{index}",
            ),
        )

    state = apply_browser_research_command(
        state,
        {
            **_command(
                "save_evidence_checkpoint",
                "600003",
                "checkpoint-replace",
            ),
            "timestamp": "2026-08-04T12:00:00+00:00",
        },
    )

    checkpoints = state["evidence_checkpoints"]
    assert len(checkpoints) == MAX_EVIDENCE_CHECKPOINTS
    assert checkpoints[0]["canonical_code"] == "600003.SH"
    assert checkpoints[0]["evidence_checked_at"] == (
        "2026-08-04T12:00:00+00:00"
    )


def test_untrusted_browser_state_is_sanitised() -> None:
    raw = {
        "version": 999,
        "recent": [
            _company("600519", "贵州茅台"),
            _company("600519", "重复公司"),
            {"code": "<script>"},
        ],
        "watchlist": "not-a-list",
        "evidence_checkpoints": [
            {
                **_company("600000"),
                "evidence_checked_at": "not-a-date",
            }
        ],
        "last_command_id": "x" * 200,
        "storage_status": "invented",
    }

    result = normalise_browser_research_state(raw)

    assert result["version"] == 3
    assert len(result["recent"]) == 1
    assert result["recent"][0]["name"] == "贵州茅台"
    assert result["watchlist"] == []
    assert result["evidence_checkpoints"] == []
    assert result["storage_status"] == "pending"
    assert len(result["last_command_id"]) == 80


def _thesis_command(
    code: str,
    command_id: str,
    *,
    thesis_id: str = "thesis-1",
) -> dict[str, object]:
    return {
        **_command("save_research_thesis", code, command_id),
        "thesis_id": thesis_id,
        "hypothesis": "收入增长能够转化为经营现金流改善",
        "confirmation_criteria": "经营现金流增速不低于收入增速",
        "invalidation_criteria": "经营现金流连续两个报告期下降",
        "topic": "财务与业绩",
    }


def test_research_thesis_create_update_and_delete() -> None:
    state = apply_browser_research_command(
        {},
        _thesis_command("600519", "thesis-create"),
    )

    assert len(state["research_theses"]) == 1
    assert state["research_theses"][0]["status"] == "待核验"

    state = apply_browser_research_command(
        state,
        {
            **_command("update_research_thesis", "600519", "thesis-update"),
            "thesis_id": "thesis-1",
            "status": "暂有证据支持",
            "review_note": "已人工核对公告原文，仍需等待下一期现金流。",
            "evidence_title": "贵州茅台2025年年度报告",
            "evidence_url": (
                "https://static.cninfo.com.cn/finalpage/"
                "2026-04-01/1234567890.PDF"
            ),
            "evidence_date": "2026-04-01",
        },
    )

    thesis = state["research_theses"][0]
    assert thesis["status"] == "暂有证据支持"
    assert thesis["evidence_date"] == "2026-04-01"
    assert "人工核对" in thesis["review_note"]

    state = apply_browser_research_command(
        state,
        {
            **_command("delete_research_thesis", "600519", "thesis-delete"),
            "thesis_id": "thesis-1",
        },
    )
    assert state["research_theses"] == []


def test_research_theses_are_bounded_and_unofficial_links_are_dropped() -> None:
    state: object = {}
    for index in range(MAX_RESEARCH_THESES + 2):
        state = apply_browser_research_command(
            state,
            _thesis_command(
                "600519",
                f"thesis-create-{index}",
                thesis_id=f"thesis-{index}",
            ),
        )

    assert len(state["research_theses"]) == MAX_RESEARCH_THESES
    first_id = state["research_theses"][0]["thesis_id"]
    state = apply_browser_research_command(
        state,
        {
            **_command(
                "update_research_thesis",
                "600519",
                "thesis-malicious-link",
            ),
            "thesis_id": first_id,
            "status": "出现反方证据",
            "review_note": "链接应被丢弃，但人工状态可以保留。",
            "evidence_title": "伪造公告",
            "evidence_url": "https://example.com/fake.pdf",
            "evidence_date": "2026-08-04",
        },
    )

    thesis = state["research_theses"][0]
    assert thesis["status"] == "出现反方证据"
    assert "evidence_url" not in thesis
