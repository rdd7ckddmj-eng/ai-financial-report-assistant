"""Validated daily limit-up pool evidence for the A-share product."""

from __future__ import annotations

import math
from collections import Counter
from datetime import date
from typing import TypedDict

import pandas as pd

from src.china_stock import DataSourceError


class LimitUpBoardRow(TypedDict):
    """One validated company in a public daily limit-up pool."""

    code: str
    name: str
    daily_change: float | None
    latest_price: float | None
    amount: float | None
    circulating_market_cap: float | None
    total_market_cap: float | None
    turnover: float | None
    sealed_funds: float | None
    first_limit_time: str | None
    last_limit_time: str | None
    break_count: int | None
    limit_statistics: str
    consecutive_boards: int | None
    industry: str


class LimitUpLadderRow(TypedDict):
    """One visible level in the daily consecutive-board ladder."""

    boards: int
    company_count: int
    share: float


class LimitUpIndustryRow(TypedDict):
    """One industry's deterministic contribution to the daily pool."""

    industry: str
    company_count: int
    consecutive_count: int
    total_amount: float | None
    median_turnover: float | None


class LimitUpBoardReview(TypedDict):
    """A deterministic post-market structure review, not a forecast."""

    ladder: list[LimitUpLadderRow]
    industries: list[LimitUpIndustryRow]
    valid_first_limit_time_count: int
    early_seal_count: int
    early_seal_ratio: float | None
    valid_break_count_count: int
    resealed_count: int
    resealed_ratio: float | None
    leading_industry_share: float | None
    observations: list[str]


class LimitUpBoardSnapshot(TypedDict):
    """A compact daily wall plus transparent descriptive statistics."""

    trade_date: str
    total_count: int
    first_board_count: int
    consecutive_board_count: int
    max_consecutive_boards: int | None
    median_turnover: float | None
    leading_industry: str
    leading_industry_count: int
    review: LimitUpBoardReview
    rows: list[LimitUpBoardRow]
    source: str


def _optional_nonnegative_number(value: object) -> float | None:
    """Return one finite non-negative number or preserve it as unavailable."""
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return None
    result = float(numeric)
    if not math.isfinite(result) or result < 0:
        return None
    return result


def _optional_nonnegative_integer(value: object) -> int | None:
    """Return one non-negative integer without inventing a missing value."""
    numeric = _optional_nonnegative_number(value)
    if numeric is None:
        return None
    return int(numeric)


def _normalise_board_time(value: object) -> str | None:
    """Normalise provider times such as 92500 or 09:25:00."""
    if value is None or pd.isna(value):
        return None
    digits = "".join(
        character for character in str(value) if character.isdigit()
    )
    if not digits:
        return None
    digits = digits.zfill(6)[-6:]
    hour = int(digits[:2])
    minute = int(digits[2:4])
    second = int(digits[4:])
    if hour > 23 or minute > 59 or second > 59:
        return None
    return f"{hour:02d}:{minute:02d}:{second:02d}"


def _normalise_code(value: object) -> str | None:
    """Preserve leading zeroes while rejecting non-six-digit codes."""
    raw = str(value).strip()
    if raw.endswith(".0"):
        raw = raw[:-2]
    if not raw.isdigit():
        return None
    code = raw.zfill(6)
    return code if len(code) == 6 else None


def prepare_limit_up_pool(frame: pd.DataFrame) -> list[LimitUpBoardRow]:
    """Validate and translate the public provider's Chinese field names."""
    if frame.empty:
        return []

    aliases = {
        "代码": "code",
        "code": "code",
        "名称": "name",
        "name": "name",
        "涨跌幅": "daily_change",
        "daily_change": "daily_change",
        "最新价": "latest_price",
        "latest_price": "latest_price",
        "成交额": "amount",
        "amount": "amount",
        "流通市值": "circulating_market_cap",
        "circulating_market_cap": "circulating_market_cap",
        "总市值": "total_market_cap",
        "total_market_cap": "total_market_cap",
        "换手率": "turnover",
        "turnover": "turnover",
        "封板资金": "sealed_funds",
        "sealed_funds": "sealed_funds",
        "首次封板时间": "first_limit_time",
        "first_limit_time": "first_limit_time",
        "最后封板时间": "last_limit_time",
        "last_limit_time": "last_limit_time",
        "炸板次数": "break_count",
        "break_count": "break_count",
        "涨停统计": "limit_statistics",
        "limit_statistics": "limit_statistics",
        "连板数": "consecutive_boards",
        "consecutive_boards": "consecutive_boards",
        "所属行业": "industry",
        "industry": "industry",
    }
    renamed = frame.rename(
        columns={
            column: aliases.get(str(column).strip(), str(column).strip())
            for column in frame.columns
        }
    )
    if not {"code", "name"}.issubset(renamed.columns):
        raise ValueError("涨停股池缺少股票代码或公司名称。")

    rows: list[LimitUpBoardRow] = []
    seen: set[str] = set()
    for item in renamed.to_dict(orient="records"):
        code = _normalise_code(item.get("code"))
        name = str(item.get("name", "")).strip()
        if code is None or not name or name.lower() == "nan" or code in seen:
            continue
        seen.add(code)

        daily_change_percent = _optional_nonnegative_number(
            item.get("daily_change")
        )
        turnover_percent = _optional_nonnegative_number(item.get("turnover"))
        consecutive_boards = _optional_nonnegative_integer(
            item.get("consecutive_boards")
        )
        if consecutive_boards == 0:
            consecutive_boards = None
        industry = str(item.get("industry", "")).strip()
        if not industry or industry.lower() == "nan":
            industry = "未分类"
        limit_statistics = str(item.get("limit_statistics", "")).strip()
        if limit_statistics.lower() == "nan":
            limit_statistics = ""

        rows.append(
            {
                "code": code,
                "name": name,
                "daily_change": (
                    None
                    if daily_change_percent is None
                    else daily_change_percent / 100
                ),
                "latest_price": _optional_nonnegative_number(
                    item.get("latest_price")
                ),
                "amount": _optional_nonnegative_number(item.get("amount")),
                "circulating_market_cap": _optional_nonnegative_number(
                    item.get("circulating_market_cap")
                ),
                "total_market_cap": _optional_nonnegative_number(
                    item.get("total_market_cap")
                ),
                "turnover": (
                    None
                    if turnover_percent is None
                    else turnover_percent / 100
                ),
                "sealed_funds": _optional_nonnegative_number(
                    item.get("sealed_funds")
                ),
                "first_limit_time": _normalise_board_time(
                    item.get("first_limit_time")
                ),
                "last_limit_time": _normalise_board_time(
                    item.get("last_limit_time")
                ),
                "break_count": _optional_nonnegative_integer(
                    item.get("break_count")
                ),
                "limit_statistics": limit_statistics,
                "consecutive_boards": consecutive_boards,
                "industry": industry,
            }
        )
    return rows


def rank_limit_up_rows(
    rows: list[LimitUpBoardRow],
) -> list[LimitUpBoardRow]:
    """Rank visible evidence without converting it into a trading score."""

    def sort_key(row: LimitUpBoardRow) -> tuple[object, ...]:
        consecutive_boards = row["consecutive_boards"]
        break_count = row["break_count"]
        sealed_funds = row["sealed_funds"]
        turnover = row["turnover"]
        return (
            -(consecutive_boards if consecutive_boards is not None else 0),
            break_count if break_count is not None else math.inf,
            row["first_limit_time"] or "99:99:99",
            -(sealed_funds if sealed_funds is not None else -1),
            -(turnover if turnover is not None else -1),
            row["code"],
        )

    return sorted(rows, key=sort_key)


def build_limit_up_board_review(
    rows: list[LimitUpBoardRow],
) -> LimitUpBoardReview:
    """Summarise the day's structure using only validated pool fields."""
    total_count = len(rows)
    board_counts = Counter(
        row["consecutive_boards"]
        for row in rows
        if row["consecutive_boards"] is not None
    )
    ladder = [
        {
            "boards": boards,
            "company_count": company_count,
            "share": company_count / total_count,
        }
        for boards, company_count in sorted(
            board_counts.items(),
            reverse=True,
        )
        if total_count > 0
    ]

    industry_groups: dict[str, list[LimitUpBoardRow]] = {}
    for row in rows:
        if row["industry"] == "未分类":
            continue
        industry_groups.setdefault(row["industry"], []).append(row)

    industries: list[LimitUpIndustryRow] = []
    for industry, industry_rows in industry_groups.items():
        amounts = [
            row["amount"]
            for row in industry_rows
            if row["amount"] is not None
        ]
        turnovers = [
            row["turnover"]
            for row in industry_rows
            if row["turnover"] is not None
        ]
        industries.append(
            {
                "industry": industry,
                "company_count": len(industry_rows),
                "consecutive_count": sum(
                    (
                        row["consecutive_boards"] is not None
                        and row["consecutive_boards"] >= 2
                    )
                    for row in industry_rows
                ),
                "total_amount": sum(amounts) if amounts else None,
                "median_turnover": (
                    float(pd.Series(turnovers).median())
                    if turnovers
                    else None
                ),
            }
        )
    industries.sort(
        key=lambda row: (
            -row["company_count"],
            -row["consecutive_count"],
            -(
                row["total_amount"]
                if row["total_amount"] is not None
                else -1
            ),
            row["industry"],
        )
    )

    valid_first_times = [
        row["first_limit_time"]
        for row in rows
        if row["first_limit_time"] is not None
    ]
    early_seal_count = sum(
        first_time <= "10:00:00" for first_time in valid_first_times
    )
    early_seal_ratio = (
        early_seal_count / len(valid_first_times)
        if valid_first_times
        else None
    )

    valid_break_counts = [
        row["break_count"]
        for row in rows
        if row["break_count"] is not None
    ]
    resealed_count = sum(
        break_count > 0 for break_count in valid_break_counts
    )
    resealed_ratio = (
        resealed_count / len(valid_break_counts)
        if valid_break_counts
        else None
    )

    leading_industry_share = (
        industries[0]["company_count"] / total_count
        if industries and total_count > 0
        else None
    )
    first_board_count = board_counts.get(1, 0)
    consecutive_board_count = sum(
        company_count
        for boards, company_count in board_counts.items()
        if boards >= 2
    )
    maximum_boards = max(board_counts) if board_counts else None
    observations = [
        (
            f"梯队结构：首板 {first_board_count} 家，连板 "
            f"{consecutive_board_count} 家，最高"
            f"{'数据不足' if maximum_boards is None else f'{maximum_boards} 板'}。"
        )
    ]
    if industries and leading_industry_share is not None:
        if leading_industry_share >= 0.25:
            concentration_text = "头部行业集中度较高"
        elif leading_industry_share >= 0.15:
            concentration_text = "存在一定行业集中"
        else:
            concentration_text = "行业分布相对分散"
        observations.append(
            f"行业结构：{industries[0]['industry']}有 "
            f"{industries[0]['company_count']} 家，占当日涨停 "
            f"{leading_industry_share:.1%}，{concentration_text}。"
        )
    else:
        observations.append("行业结构：有效行业分类数据不足。")

    if early_seal_ratio is None:
        observations.append("封板节奏：有效首次封板时间数据不足。")
    else:
        observations.append(
            f"封板节奏：{early_seal_count}/{len(valid_first_times)} 家"
            f"在 10:00 前首次封板，占有效记录 {early_seal_ratio:.1%}。"
        )

    if resealed_ratio is None:
        observations.append("回封记录：有效炸板次数数据不足。")
    else:
        observations.append(
            f"回封记录：{resealed_count}/{len(valid_break_counts)} 家"
            f"存在至少一次开板后回封，占有效记录 {resealed_ratio:.1%}。"
        )

    return {
        "ladder": ladder,
        "industries": industries,
        "valid_first_limit_time_count": len(valid_first_times),
        "early_seal_count": early_seal_count,
        "early_seal_ratio": early_seal_ratio,
        "valid_break_count_count": len(valid_break_counts),
        "resealed_count": resealed_count,
        "resealed_ratio": resealed_ratio,
        "leading_industry_share": leading_industry_share,
        "observations": observations,
    }


def build_limit_up_board_snapshot(
    frame: pd.DataFrame,
    trade_date: date,
    *,
    max_rows: int = 200,
) -> LimitUpBoardSnapshot:
    """Build the daily board wall and keep its size bounded."""
    if max_rows <= 0:
        raise ValueError("涨停板展示上限必须大于零。")
    rows = prepare_limit_up_pool(frame)
    ranked = rank_limit_up_rows(rows)
    consecutive_values = [
        row["consecutive_boards"]
        for row in rows
        if row["consecutive_boards"] is not None
    ]
    turnovers = [
        row["turnover"] for row in rows if row["turnover"] is not None
    ]
    industry_counts = Counter(
        row["industry"] for row in rows if row["industry"] != "未分类"
    )
    leading_industry = "数据不足"
    leading_industry_count = 0
    if industry_counts:
        leading_industry, leading_industry_count = sorted(
            industry_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )[0]

    return {
        "trade_date": trade_date.isoformat(),
        "total_count": len(rows),
        "first_board_count": sum(
            row["consecutive_boards"] == 1 for row in rows
        ),
        "consecutive_board_count": sum(
            (
                row["consecutive_boards"] is not None
                and row["consecutive_boards"] >= 2
            )
            for row in rows
        ),
        "max_consecutive_boards": (
            max(consecutive_values) if consecutive_values else None
        ),
        "median_turnover": (
            float(pd.Series(turnovers).median()) if turnovers else None
        ),
        "leading_industry": leading_industry,
        "leading_industry_count": leading_industry_count,
        "review": build_limit_up_board_review(rows),
        "rows": ranked[:max_rows],
        "source": "东方财富涨停板行情公开涨停股池",
    }


def fetch_limit_up_pool(trade_date: date) -> pd.DataFrame:
    """Fetch one recent daily limit-up pool through the provider adapter."""
    try:
        import akshare as ak

        frame = ak.stock_zt_pool_em(date=trade_date.strftime("%Y%m%d"))
    except Exception as error:
        raise DataSourceError(
            "当前无法读取该日涨停股池，请稍后重试或选择近期交易日。"
        ) from error
    if not isinstance(frame, pd.DataFrame):
        raise DataSourceError("涨停股池返回格式异常，请稍后重试。")
    return frame
