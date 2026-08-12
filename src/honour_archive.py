"""Deterministic honour records for completed learning cases.

The first release stores records in the visitor's browser only.  A device-local
rank must never be presented as a platform-wide leaderboard position.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from html import escape
from typing import Mapping, TypedDict


HONOUR_ARCHIVE_VERSION = 1
FIRST_CASE_MISSION_ID = "moutai-repurchase-publication-boundary"
FIRST_CASE_TITLE = "《消失的现金》"
FIRST_CASE_HONOUR_PREFIX = "WFZ-C01"
HONOUR_CAPABILITIES = (
    "利润与现金",
    "证据链阅读",
    "结论边界",
    "历史时点迁移",
)


class HonourRecord(TypedDict):
    """One bounded learning-achievement record."""

    version: int
    mission_id: str
    case_title: str
    player_name: str
    completion_rank: int
    honour_number: str
    completed_at: str


class HonourPosterPayload(TypedDict):
    """Text and dimensions shared by poster preview and PNG renderer."""

    width: int
    height: int
    file_name: str
    player_name: str
    rank_label: str
    honour_number: str
    completed_on: str
    case_title: str
    headline: str
    story_lines: list[str]
    capabilities: list[str]
    disclaimer: str


def _clean_player_name(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.strip().split())[:12]
    return cleaned or None


def _parse_completed_at(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def format_completion_rank(rank: int) -> str:
    """Display ranks as ordinary Arabic numbers without leading zeroes."""
    if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1:
        raise ValueError("通关位次必须是大于零的整数。")
    return str(rank)


def format_honour_number(rank: int) -> str:
    """Keep the requested six-digit archive number separate from the rank."""
    rank_text = format_completion_rank(rank)
    return rank_text.zfill(6)


def build_honour_record(
    player_name: str,
    *,
    completion_rank: int = 1,
    completed_at: datetime | None = None,
) -> HonourRecord:
    """Create a safe fallback record before browser storage replies."""
    cleaned_name = _clean_player_name(player_name)
    if cleaned_name is None:
        raise ValueError("荣誉档案需要有效的调查员代号。")
    format_completion_rank(completion_rank)
    timestamp = completed_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    timestamp = timestamp.astimezone(timezone.utc)
    return {
        "version": HONOUR_ARCHIVE_VERSION,
        "mission_id": FIRST_CASE_MISSION_ID,
        "case_title": FIRST_CASE_TITLE,
        "player_name": cleaned_name,
        "completion_rank": completion_rank,
        "honour_number": format_honour_number(completion_rank),
        "completed_at": timestamp.isoformat(timespec="seconds"),
    }


def normalise_honour_record(value: object) -> HonourRecord | None:
    """Validate the browser-provided record before it reaches the page."""
    if not isinstance(value, Mapping):
        return None
    if value.get("version") != HONOUR_ARCHIVE_VERSION:
        return None
    if value.get("mission_id") != FIRST_CASE_MISSION_ID:
        return None
    if value.get("case_title") != FIRST_CASE_TITLE:
        return None

    player_name = _clean_player_name(value.get("player_name"))
    rank = value.get("completion_rank")
    if (
        player_name is None
        or isinstance(rank, bool)
        or not isinstance(rank, int)
        or not 1 <= rank <= 999_999_999
    ):
        return None
    expected_number = format_honour_number(rank)
    if value.get("honour_number") != expected_number:
        return None
    completed_at = _parse_completed_at(value.get("completed_at"))
    if completed_at is None:
        return None
    return {
        "version": HONOUR_ARCHIVE_VERSION,
        "mission_id": FIRST_CASE_MISSION_ID,
        "case_title": FIRST_CASE_TITLE,
        "player_name": player_name,
        "completion_rank": rank,
        "honour_number": expected_number,
        "completed_at": completed_at.isoformat(timespec="seconds"),
    }


def honour_completed_on(record: HonourRecord) -> date:
    """Return the stable UTC completion date used on both layouts."""
    completed_at = _parse_completed_at(record["completed_at"])
    if completed_at is None:  # pragma: no cover - guarded by typed builders.
        raise ValueError("荣誉档案完成时间无效。")
    return completed_at.date()


def build_honour_archive_html(record: HonourRecord) -> str:
    """Build the horizontal archive with escaped dynamic content."""
    player_name = escape(record["player_name"])
    rank = format_completion_rank(record["completion_rank"])
    completed_on = honour_completed_on(record)
    capability_html = "".join(
        f'<span class="wfz-honour-skill">{escape(item)}</span>'
        for item in HONOUR_CAPABILITIES
    )
    return f"""
    <section class="wfz-honour-archive">
        <div class="wfz-honour-topline">
            <span>FANGZHENG AI · RESEARCHER MISSION BUREAU</span>
            <span class="wfz-honour-seal">CASE 01 · ARCHIVED</span>
        </div>
        <div class="wfz-honour-grid">
            <div class="wfz-honour-main">
                <div class="wfz-honour-kicker">首案完整通关纪念</div>
                <h1>研究员<br><span>荣誉档案</span></h1>
                <p class="wfz-honour-story">
                    起初，所有人都在等一个漂亮答案。你却把结论停在证据
                    边界之前，穿过六个阶段，回到真实时间线，拒绝用明天
                    解释今天。现在，首案正式封存。
                </p>
                <div class="wfz-honour-name">
                    <small>ARCHIVED FOR / 调查员</small>
                    <strong>{player_name}</strong>
                </div>
            </div>
            <aside class="wfz-honour-rank">
                <div class="wfz-honour-rank-label">
                    测试赛季 · 本设备通关位次
                </div>
                <div class="wfz-honour-rank-number">{rank}</div>
                <div class="wfz-honour-meta">
                    <span>荣誉编号</span>
                    <strong>{record['honour_number']}</strong>
                </div>
                <div class="wfz-honour-meta">
                    <span>完成日期</span>
                    <strong>{completed_on.isoformat()}</strong>
                </div>
            </aside>
        </div>
        <div class="wfz-honour-skills">{capability_html}</div>
        <div class="wfz-honour-footer">
            <span>学习成就纪念，不代表职业资格、执业许可或投资能力认证。</span>
            <strong>产品设计与研发 · 王方正 · Durham University</strong>
        </div>
    </section>
    """


def build_honour_poster_payload(record: HonourRecord) -> HonourPosterPayload:
    """Build original, social-ready copy without borrowing source wording."""
    completed_on = honour_completed_on(record)
    return {
        "width": 1080,
        "height": 1920,
        "file_name": (
            f"FANGZHENG_AI_{FIRST_CASE_HONOUR_PREFIX}_"
            f"{record['honour_number']}_竖版荣誉档案.png"
        ),
        "player_name": record["player_name"],
        "rank_label": format_completion_rank(record["completion_rank"]),
        "honour_number": record["honour_number"],
        "completed_on": completed_on.isoformat(),
        "case_title": FIRST_CASE_TITLE,
        "headline": "首案封存｜拒绝用明天解释今天",
        "story_lines": [
            "起初，所有人都在等一个漂亮答案。",
            "你却停在证据边界之前，",
            "穿过教学、练习、调查、证据链与答辩，",
            "最后回到真实历史时点，",
            "把公开日与交易日重新分开。",
            "最难的从来不是找到数字，",
            "而是知道什么仍然不能下结论。",
        ],
        "capabilities": list(HONOUR_CAPABILITIES),
        "disclaimer": (
            "学习成就纪念｜不代表职业资格、执业许可或投资能力认证"
        ),
    }
