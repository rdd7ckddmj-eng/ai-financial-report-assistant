"""Validated helpers for Chinese listed-company research.

The external data provider is intentionally kept behind a small set of
functions.  Financial and market calculations remain deterministic Python
logic, while the interface can fall back gracefully if a public source is
temporarily unavailable.
"""

from __future__ import annotations

import json
import math
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from functools import lru_cache
from typing import TypedDict
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

import pandas as pd


class CompanyIdentity(TypedDict):
    """One canonical A-share company identity."""

    code: str
    name: str
    exchange: str
    exchange_name: str
    canonical_code: str


class MarketMetrics(TypedDict):
    """Deterministic statistics calculated from closing prices."""

    latest_close: float
    latest_date: str
    daily_change: float | None
    return_20d: float | None
    return_60d: float | None
    return_250d: float | None
    annualised_volatility: float | None
    max_drawdown: float | None
    observations: int


class MarketActivityEvidence(TypedDict):
    """Latest-session activity signals with explicit evidence limitations."""

    latest_date: str
    daily_return: float | None
    volume_ratio_20d: float | None
    volume_signal: str
    volume_percentile_250d: float | None
    volume_percentile_sessions: int
    turnover: float | None
    turnover_status: str
    turnover_percentile_250d: float | None
    turnover_percentile_sessions: int
    effective_turnover: float | None
    effective_turnover_status: str
    limit_up_reference: float
    limit_up_status: str
    limit_up_note: str


class MarketActivityEvent(TypedDict):
    """One deterministically screened trading day for historical review."""

    date: str
    event_type: str
    close: float
    daily_return: float | None
    daily_return_basis: str
    volume_ratio_20d: float | None
    volume_percentile_250d: float | None
    turnover: float | None
    turnover_percentile_250d: float | None
    turnover_high_candidate: bool
    limit_up_reference: float
    limit_up_candidate: bool


class DataSourceError(RuntimeError):
    """Raised when a public market-data source cannot be used safely."""


EXCHANGE_NAMES = {
    "SH": "上海证券交易所",
    "SZ": "深圳证券交易所",
    "BJ": "北京证券交易所",
}

CNINFO_STOCK_DIRECTORY_URL = (
    "https://www.cninfo.com.cn/new/data/szse_stock.json"
)
CNINFO_ANNOUNCEMENT_QUERY_URL = (
    "https://www.cninfo.com.cn/new/hisAnnouncement/query"
)
CNINFO_REQUEST_TIMEOUT_SECONDS = 6.0
CNINFO_MAX_RESPONSE_BYTES = 8 * 1024 * 1024
CNINFO_PAGE_SIZE = 30
CNINFO_MAX_PAGES = 10
CNINFO_MAX_WORKERS = 4
CNINFO_CATEGORY_CODES = {
    "年报": "category_ndbg_szsh",
    "半年报": "category_bndbg_szsh",
    "一季报": "category_yjdbg_szsh",
    "三季报": "category_sjdbg_szsh",
    "业绩预告": "category_yjygjxz_szsh",
    "权益分派": "category_qyfpxzcs_szsh",
    "董事会": "category_dshgg_szsh",
    "监事会": "category_jshgg_szsh",
    "股东大会": "category_gddh_szsh",
    "日常经营": "category_rcjy_szsh",
    "公司治理": "category_gszl_szsh",
    "中介报告": "category_zj_szsh",
    "首发": "category_sf_szsh",
    "增发": "category_zf_szsh",
    "股权激励": "category_gqjl_szsh",
    "配股": "category_pg_szsh",
    "解禁": "category_jj_szsh",
    "公司债": "category_gszq_szsh",
    "可转债": "category_kzzq_szsh",
    "其他融资": "category_qtrz_szsh",
    "股权变动": "category_gqbd_szsh",
    "补充更正": "category_bcgz_szsh",
    "澄清致歉": "category_cqdq_szsh",
    "风险提示": "category_fxts_szsh",
    "特别处理和退市": "category_tbclts_szsh",
    "退市整理期": "category_tszlq_szsh",
}

# A small offline directory keeps the product demonstrable when the live
# company directory is temporarily unavailable.  It is not used as a market
# data cache or as a substitute for current official information.
KNOWN_COMPANIES = {
    "600519": "贵州茅台",
    "601398": "工商银行",
    "601318": "中国平安",
    "601857": "中国石油",
    "000001": "平安银行",
    "000002": "万科A",
    "000568": "泸州老窖",
    "000858": "五粮液",
    "002594": "比亚迪",
    "300750": "宁德时代",
    "688981": "中芯国际",
}

CODE_PATTERN = re.compile(
    r"(?<!\d)(?:(?:SH|SZ|BJ)[.\s-]*)?(\d{6})"
    r"(?:[.\s-]*(?:SH|SZ|BJ))?(?!\d)",
    re.IGNORECASE,
)


def infer_exchange(code: str) -> str:
    """Infer the mainland exchange from a six-digit listed-company code."""
    clean_code = str(code).strip()
    if not re.fullmatch(r"\d{6}", clean_code):
        raise ValueError("股票代码必须是6位数字。")

    if clean_code.startswith(("600", "601", "603", "605", "688", "689")):
        return "SH"
    if clean_code.startswith(
        ("000", "001", "002", "003", "300", "301")
    ):
        return "SZ"
    if clean_code.startswith(("4", "8", "920")):
        return "BJ"
    raise ValueError("暂时无法确认该代码所属的沪、深或北交所。")


def build_company_identity(
    code: str,
    name: str | None = None,
) -> CompanyIdentity:
    """Build one exchange-qualified company identity."""
    clean_code = str(code).strip()
    exchange = infer_exchange(clean_code)
    company_name = (name or KNOWN_COMPANIES.get(clean_code) or "待核验公司")
    return {
        "code": clean_code,
        "name": str(company_name).strip(),
        "exchange": exchange,
        "exchange_name": EXCHANGE_NAMES[exchange],
        "canonical_code": f"{clean_code}.{exchange}",
    }


def prepare_company_directory(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalise a provider company directory to code and name columns."""
    if frame.empty:
        return pd.DataFrame(columns=["code", "name"])

    aliases = {
        "code": "code",
        "代码": "code",
        "股票代码": "code",
        "证券代码": "code",
        "name": "name",
        "名称": "name",
        "股票简称": "name",
        "证券简称": "name",
    }
    renamed = frame.rename(
        columns={
            column: aliases.get(str(column).strip(), str(column).strip())
            for column in frame.columns
        }
    )
    if not {"code", "name"}.issubset(renamed.columns):
        raise ValueError("公司目录缺少股票代码或公司名称字段。")

    result = renamed.loc[:, ["code", "name"]].copy()
    result["code"] = (
        result["code"].astype(str).str.extract(r"(\d{6})", expand=False)
    )
    result["name"] = result["name"].astype(str).str.strip()
    result = result.dropna().drop_duplicates(subset=["code"], keep="first")
    return result.reset_index(drop=True)


def _normalise_name(value: str) -> str:
    """Create a comparable company-name key without changing display text."""
    return (
        str(value)
        .strip()
        .upper()
        .replace(" ", "")
        .replace("　", "")
        .replace("Ａ", "A")
        .replace("*", "")
    )


def resolve_company(
    query: str,
    directory: pd.DataFrame | None = None,
    *,
    max_results: int = 8,
) -> list[CompanyIdentity]:
    """Resolve a user-entered code or company name to canonical identities."""
    clean_query = str(query).strip()
    if not clean_query:
        return []

    code_match = CODE_PATTERN.search(clean_query)
    if code_match:
        code = code_match.group(1)
        name = KNOWN_COMPANIES.get(code)
        if directory is not None and not directory.empty:
            prepared = prepare_company_directory(directory)
            selected = prepared.loc[prepared["code"] == code, "name"]
            if not selected.empty:
                name = str(selected.iloc[0])
        try:
            return [build_company_identity(code, name)]
        except ValueError:
            return []

    if directory is None or directory.empty:
        offline_rows = pd.DataFrame(
            [
                {"code": code, "name": name}
                for code, name in KNOWN_COMPANIES.items()
            ]
        )
        prepared = offline_rows
    else:
        prepared = prepare_company_directory(directory)

    search_key = _normalise_name(clean_query)
    names = prepared["name"].map(_normalise_name)
    exact = prepared.loc[names == search_key]
    candidates = exact if not exact.empty else prepared.loc[
        names.str.contains(re.escape(search_key), na=False)
    ]

    results: list[CompanyIdentity] = []
    for row in candidates.head(max_results).itertuples(index=False):
        try:
            results.append(build_company_identity(row.code, row.name))
        except ValueError:
            continue
    return results


def prepare_market_history(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate and standardise daily OHLCV history from a provider."""
    source_attributes = dict(frame.attrs)
    if frame.empty:
        empty = pd.DataFrame(
            columns=[
                "date",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "amount",
                "pct_change",
                "turnover",
            ]
        )
        empty.attrs.update(source_attributes)
        return empty

    aliases = {
        "日期": "date",
        "date": "date",
        "开盘": "open",
        "open": "open",
        "最高": "high",
        "high": "high",
        "最低": "low",
        "low": "low",
        "收盘": "close",
        "close": "close",
        "成交量": "volume",
        "volume": "volume",
        "成交额": "amount",
        "amount": "amount",
        "涨跌幅": "pct_change",
        "pct_change": "pct_change",
        "换手率": "turnover",
        "turnover": "turnover",
    }
    renamed = frame.rename(
        columns={
            column: aliases.get(str(column).strip(), str(column).strip())
            for column in frame.columns
        }
    )
    required = {"date", "open", "high", "low", "close", "volume"}
    if not required.issubset(renamed.columns):
        missing = "、".join(sorted(required - set(renamed.columns)))
        raise ValueError(f"行情数据缺少必要字段：{missing}。")

    result = renamed.copy()
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    for column in (
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "pct_change",
        "turnover",
    ):
        if column not in result.columns:
            result[column] = math.nan
        result[column] = pd.to_numeric(result[column], errors="coerce")

    result = result.dropna(
        subset=["date", "open", "high", "low", "close", "volume"]
    )
    valid_ohlc = (
        (result["high"] >= result[["open", "close", "low"]].max(axis=1))
        & (result["low"] <= result[["open", "close", "high"]].min(axis=1))
        & (result[["open", "high", "low", "close"]] > 0).all(axis=1)
        & (result["volume"] >= 0)
    )
    result = result.loc[valid_ohlc]
    result = result.sort_values("date").drop_duplicates(
        subset=["date"],
        keep="last",
    )
    result["date"] = result["date"].dt.date
    prepared = result.loc[
        :,
        [
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
            "pct_change",
            "turnover",
        ],
    ].reset_index(drop=True)
    prepared.attrs.update(source_attributes)
    return prepared


def prepare_tencent_market_history(frame: pd.DataFrame) -> pd.DataFrame:
    """Adapt AKShare's Tencent daily schema to the validated OHLCV schema."""
    adapted = frame.copy()
    normalised_columns = {
        str(column).strip().lower(): column for column in adapted.columns
    }
    if "volume" not in normalised_columns and "amount" in normalised_columns:
        # The Tencent adapter names its final field ``amount`` although the
        # documented daily examples contain the traded-volume series there.
        source_column = normalised_columns["amount"]
        adapted["volume"] = adapted[source_column]
        adapted = adapted.drop(columns=[source_column])
    return prepare_market_history(adapted)


def prepare_sina_turnover_history(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert Sina circulating-share data into ordinary turnover percentages.

    AKShare's Sina adapter defines turnover as traded shares divided by
    circulating shares and returns it as a decimal fraction.  The application's
    standard market-history schema stores turnover in percentage points, so a
    value such as ``0.0047`` becomes ``0.47`` before it is merged by date.
    """
    empty = pd.DataFrame(columns=["date", "turnover"])
    if frame.empty:
        return empty

    aliases = {
        "日期": "date",
        "date": "date",
        "成交量": "volume",
        "volume": "volume",
        "流通股本": "outstanding_share",
        "outstanding_share": "outstanding_share",
        "换手率": "turnover",
        "turnover": "turnover",
    }
    renamed = frame.rename(
        columns={
            column: aliases.get(str(column).strip(), str(column).strip())
            for column in frame.columns
        }
    )
    if "date" not in renamed.columns:
        raise ValueError("新浪换手率数据缺少交易日期。")

    result = pd.DataFrame(index=renamed.index)
    result["date"] = pd.to_datetime(renamed["date"], errors="coerce")
    provider_turnover = pd.to_numeric(
        renamed.get(
            "turnover",
            pd.Series(math.nan, index=renamed.index),
        ),
        errors="coerce",
    )
    volume = pd.to_numeric(
        renamed.get(
            "volume",
            pd.Series(math.nan, index=renamed.index),
        ),
        errors="coerce",
    )
    outstanding_share = pd.to_numeric(
        renamed.get(
            "outstanding_share",
            pd.Series(math.nan, index=renamed.index),
        ),
        errors="coerce",
    )

    # Prefer the transparent formula documented by the source.  The provider's
    # own turnover field is retained as a fallback when either input is absent.
    calculated_fraction = volume / outstanding_share.where(
        outstanding_share > 0
    )
    turnover_fraction = calculated_fraction.where(
        calculated_fraction.notna(),
        provider_turnover,
    )
    result["turnover"] = turnover_fraction * 100
    result = result.dropna(subset=["date", "turnover"])
    result = result.loc[
        result["turnover"].map(math.isfinite) & (result["turnover"] >= 0)
    ]
    result = result.sort_values("date").drop_duplicates(
        subset=["date"],
        keep="last",
    )
    result["date"] = result["date"].dt.date
    prepared = result.loc[:, ["date", "turnover"]].reset_index(drop=True)
    prepared.attrs["turnover_source"] = (
        "新浪财经流通股本计算（成交量÷流通股本）"
    )
    return prepared


def merge_turnover_history(
    market_history: pd.DataFrame,
    turnover_history: pd.DataFrame,
) -> pd.DataFrame:
    """Fill missing ordinary turnover without replacing primary-source values."""
    prepared_market = prepare_market_history(market_history)
    source_attributes = dict(prepared_market.attrs)
    prepared_turnover = prepare_sina_turnover_history(turnover_history)
    if prepared_market.empty or prepared_turnover.empty:
        return prepared_market

    merged = prepared_market.merge(
        prepared_turnover.rename(
            columns={"turnover": "supplemental_turnover"}
        ),
        on="date",
        how="left",
        validate="one_to_one",
    )
    missing_before = merged["turnover"].isna()
    merged["turnover"] = merged["turnover"].where(
        ~missing_before,
        merged["supplemental_turnover"],
    )
    filled_rows = int(
        (missing_before & merged["turnover"].notna()).sum()
    )
    merged = merged.drop(columns=["supplemental_turnover"])
    merged.attrs.update(source_attributes)
    if filled_rows:
        merged.attrs["turnover_source"] = prepared_turnover.attrs[
            "turnover_source"
        ]
        merged.attrs["turnover_rows_filled"] = filled_rows
    return merged


def merge_direct_turnover_history(
    market_history: pd.DataFrame,
    provider_history: pd.DataFrame,
    *,
    source_label: str,
) -> pd.DataFrame:
    """Fill ordinary turnover from a second bounded daily-history response.

    Both inputs use the application's percentage-point convention.  Only the
    date and turnover columns from the supplemental source survive the merge,
    keeping the temporary frame small on the free Render instance.
    """
    prepared_market = prepare_market_history(market_history)
    source_attributes = dict(prepared_market.attrs)
    prepared_provider = prepare_market_history(provider_history)
    if prepared_market.empty or prepared_provider.empty:
        return prepared_market

    supplemental = prepared_provider.loc[:, ["date", "turnover"]].dropna(
        subset=["date", "turnover"]
    )
    supplemental = supplemental.loc[
        supplemental["turnover"].map(math.isfinite)
        & (supplemental["turnover"] >= 0)
    ]
    if supplemental.empty:
        return prepared_market

    merged = prepared_market.merge(
        supplemental.rename(
            columns={"turnover": "supplemental_turnover"}
        ),
        on="date",
        how="left",
        validate="one_to_one",
    )
    missing_before = merged["turnover"].isna()
    merged["turnover"] = merged["turnover"].where(
        ~missing_before,
        merged["supplemental_turnover"],
    )
    filled_rows = int(
        (missing_before & merged["turnover"].notna()).sum()
    )
    merged = merged.drop(columns=["supplemental_turnover"])
    merged.attrs.update(source_attributes)
    if filled_rows:
        merged.attrs["turnover_source"] = source_label
        merged.attrs["turnover_rows_filled"] = filled_rows
    return merged


def add_moving_averages(
    frame: pd.DataFrame,
    windows: tuple[int, ...] = (5, 20, 60),
) -> pd.DataFrame:
    """Add transparent rolling close averages used by the K-line page."""
    result = frame.copy()
    for window in windows:
        result[f"ma_{window}"] = result["close"].rolling(window).mean()
    return result


def _period_return(close: pd.Series, trading_days: int) -> float | None:
    """Calculate a point-to-point return when enough observations exist."""
    if len(close) <= trading_days:
        return None
    base = float(close.iloc[-trading_days - 1])
    if base == 0:
        return None
    return float(close.iloc[-1] / base - 1)


def calculate_market_metrics(frame: pd.DataFrame) -> MarketMetrics:
    """Calculate market statistics without asking an LLM to do arithmetic."""
    prepared = prepare_market_history(frame)
    if prepared.empty:
        raise ValueError("没有足够的有效行情数据用于计算。")

    close = prepared["close"].astype(float)
    daily_returns = close.pct_change().dropna()
    volatility = (
        float(daily_returns.std(ddof=1) * math.sqrt(250))
        if len(daily_returns) >= 2
        else None
    )
    drawdowns = close / close.cummax() - 1
    daily_change = (
        float(close.iloc[-1] / close.iloc[-2] - 1)
        if len(close) >= 2
        else None
    )

    return {
        "latest_close": float(close.iloc[-1]),
        "latest_date": prepared["date"].iloc[-1].isoformat(),
        "daily_change": daily_change,
        "return_20d": _period_return(close, 20),
        "return_60d": _period_return(close, 60),
        "return_250d": _period_return(close, 250),
        "annualised_volatility": volatility,
        "max_drawdown": float(drawdowns.min()),
        "observations": len(prepared),
    }


def _is_risk_warning_company(company: CompanyIdentity) -> bool:
    """Identify an explicit ST marker without guessing from price behaviour."""
    compact_name = re.sub(r"\s+", "", company["name"]).upper()
    return compact_name.startswith(("ST", "*ST"))


def reference_price_limit_ratio(
    company: CompanyIdentity,
    market_date: date,
) -> float:
    """Return the board-level daily price-limit reference for one stock.

    This is a screening reference, not a definitive exchange determination.
    IPO windows, relistings, and other rule exceptions need separate metadata.
    """
    code = company["code"]
    if company["exchange"] == "BJ":
        return 0.30
    if code.startswith(("300", "301", "688", "689")):
        return 0.20
    if _is_risk_warning_company(company):
        # Shanghai aligned main-board risk-warning stocks with the 10% limit
        # from 2026-07-06. Shenzhen risk-warning stocks remain a 5% reference.
        if company["exchange"] == "SH" and market_date >= date(2026, 7, 6):
            return 0.10
        return 0.05
    return 0.10


def _prior_session_percentile(
    current_value: float,
    prior_values: pd.Series,
    *,
    lookback_sessions: int = 250,
    minimum_sessions: int = 20,
) -> tuple[float | None, int]:
    """Compare one observation only with valid sessions available before it.

    A mid-rank percentile avoids labelling a value as the 100th percentile
    when every prior observation is tied with it.
    """
    history = pd.to_numeric(
        prior_values.tail(lookback_sessions),
        errors="coerce",
    ).dropna()
    history = history.loc[history.map(math.isfinite)]
    comparison_sessions = len(history)
    if (
        not math.isfinite(float(current_value))
        or comparison_sessions < minimum_sessions
    ):
        return None, comparison_sessions

    below = int((history < current_value).sum())
    tied = int((history == current_value).sum())
    percentile = (below + 0.5 * tied) / comparison_sessions
    return float(percentile), comparison_sessions


def calculate_market_activity(
    frame: pd.DataFrame,
    company: CompanyIdentity,
) -> MarketActivityEvidence:
    """Calculate latest-session activity evidence without an LLM."""
    prepared = prepare_market_history(frame)
    if prepared.empty:
        raise ValueError("没有足够的有效行情数据用于计算市场活跃度。")

    latest = prepared.iloc[-1]
    latest_date = latest["date"]
    daily_return: float | None = None
    if not pd.isna(latest["pct_change"]):
        daily_return = float(latest["pct_change"]) / 100
    elif len(prepared) >= 2:
        previous_close = float(prepared.iloc[-2]["close"])
        if previous_close > 0:
            daily_return = float(latest["close"]) / previous_close - 1

    volume_ratio: float | None = None
    if len(prepared) >= 21:
        previous_20_volume = prepared["volume"].iloc[-21:-1].astype(float)
        baseline = float(previous_20_volume.median())
        if baseline > 0:
            volume_ratio = float(latest["volume"]) / baseline

    if volume_ratio is None:
        volume_signal = "数据不足"
    elif volume_ratio >= 2:
        volume_signal = "明显放量"
    elif volume_ratio >= 1.3:
        volume_signal = "温和放量"
    elif volume_ratio <= 0.7:
        volume_signal = "明显缩量"
    else:
        volume_signal = "接近前20日常态"

    volume_percentile, volume_percentile_sessions = (
        _prior_session_percentile(
            float(latest["volume"]),
            prepared["volume"].iloc[:-1],
        )
    )
    turnover_value = latest["turnover"]
    turnover = (
        None if pd.isna(turnover_value) else float(turnover_value) / 100
    )
    turnover_percentile, turnover_percentile_sessions = (
        _prior_session_percentile(
            (
                float("nan")
                if turnover is None
                else float(turnover_value)
            ),
            prepared["turnover"].iloc[:-1],
        )
    )
    turnover_source = str(prepared.attrs.get("turnover_source", "")).strip()
    if turnover is None:
        turnover_status = "当前公开日线未提供换手率"
    elif turnover_source:
        turnover_status = f"已取得普通换手率；来源：{turnover_source}"
    else:
        turnover_status = "公开日线已提供普通换手率"

    limit_reference = reference_price_limit_ratio(company, latest_date)
    if daily_return is None:
        limit_status = "数据不足"
    elif daily_return >= limit_reference - 0.003:
        limit_status = "涨停候选"
    else:
        limit_status = "未触及参考阈值"

    return {
        "latest_date": latest_date.isoformat(),
        "daily_return": daily_return,
        "volume_ratio_20d": volume_ratio,
        "volume_signal": volume_signal,
        "volume_percentile_250d": volume_percentile,
        "volume_percentile_sessions": volume_percentile_sessions,
        "turnover": turnover,
        "turnover_status": turnover_status,
        "turnover_percentile_250d": turnover_percentile,
        "turnover_percentile_sessions": turnover_percentile_sessions,
        "effective_turnover": None,
        "effective_turnover_status": (
            "缺少可核验的时点自由流通股本，暂不计算"
        ),
        "limit_up_reference": limit_reference,
        "limit_up_status": limit_status,
        "limit_up_note": (
            "仅按板块、风险警示标识和最新日涨幅筛选；"
            "新股前五个交易日、重新上市、退市整理首日、"
            "价格最小变动单位及其他例外仍需交易所数据复核。"
        ),
    }


def scan_market_activity_events(
    frame: pd.DataFrame,
    company: CompanyIdentity,
    *,
    lookback_sessions: int = 250,
    volume_ratio_threshold: float = 2.0,
    turnover_percentile_threshold: float = 0.90,
    max_results: int = 8,
) -> list[MarketActivityEvent]:
    """Find recent price, volume, and ordinary-turnover anomaly candidates.

    The rolling volume baseline excludes the day being tested.  Results are
    screening candidates for point-in-time research, not trading signals or
    definitive exchange classifications.
    """
    if lookback_sessions < 1:
        raise ValueError("扫描交易日数量必须大于零。")
    if volume_ratio_threshold <= 0:
        raise ValueError("成交量倍数阈值必须大于零。")
    if not 0 < turnover_percentile_threshold <= 1:
        raise ValueError("换手率历史分位阈值必须在0到1之间。")
    if max_results < 1:
        raise ValueError("最多展示数量必须大于零。")

    prepared = prepare_market_history(frame)
    if prepared.empty:
        return []

    calculated_returns = prepared["close"].astype(float).pct_change()
    provider_returns = prepared["pct_change"].astype(float) / 100
    daily_returns = provider_returns.where(
        provider_returns.notna(),
        calculated_returns,
    )
    return_basis = pd.Series(
        "页面收盘价计算",
        index=prepared.index,
        dtype="object",
    )
    return_basis.loc[provider_returns.notna()] = "公开行情源涨跌幅"

    volume = prepared["volume"].astype(float)
    previous_20_median = volume.shift(1).rolling(
        window=20,
        min_periods=20,
    ).median()
    volume_ratios = volume / previous_20_median.where(
        previous_20_median > 0
    )

    first_position = max(0, len(prepared) - lookback_sessions)
    events: list[MarketActivityEvent] = []
    for position in range(first_position, len(prepared)):
        row = prepared.iloc[position]
        market_date = row["date"]
        return_value = daily_returns.iloc[position]
        daily_return = (
            None if pd.isna(return_value) else float(return_value)
        )
        volume_ratio_value = volume_ratios.iloc[position]
        volume_ratio = (
            None
            if pd.isna(volume_ratio_value)
            else float(volume_ratio_value)
        )
        limit_reference = reference_price_limit_ratio(
            company,
            market_date,
        )
        limit_candidate = (
            daily_return is not None
            and daily_return >= limit_reference - 0.003
        )
        high_volume = (
            volume_ratio is not None
            and volume_ratio >= volume_ratio_threshold
        )
        turnover_value = row["turnover"]
        turnover = (
            None
            if pd.isna(turnover_value)
            else float(turnover_value) / 100
        )
        volume_percentile, _ = _prior_session_percentile(
            float(row["volume"]),
            prepared["volume"].iloc[:position],
        )
        turnover_percentile, _ = _prior_session_percentile(
            (
                float("nan")
                if turnover is None
                else float(turnover_value)
            ),
            prepared["turnover"].iloc[:position],
        )
        turnover_high_candidate = (
            turnover_percentile is not None
            and turnover_percentile >= turnover_percentile_threshold
        )
        if not (
            limit_candidate
            or high_volume
            or turnover_high_candidate
        ):
            continue

        event_labels = []
        if limit_candidate:
            event_labels.append("涨停候选")
        if high_volume:
            event_labels.append("明显放量")
        if turnover_high_candidate:
            event_labels.append("普通换手率高位")
        events.append(
            {
                "date": market_date.isoformat(),
                "event_type": " + ".join(event_labels),
                "close": float(row["close"]),
                "daily_return": daily_return,
                "daily_return_basis": str(return_basis.iloc[position]),
                "volume_ratio_20d": volume_ratio,
                "volume_percentile_250d": volume_percentile,
                "turnover": turnover,
                "turnover_percentile_250d": turnover_percentile,
                "turnover_high_candidate": turnover_high_candidate,
                "limit_up_reference": limit_reference,
                "limit_up_candidate": limit_candidate,
            }
        )

    return list(reversed(events))[:max_results]


def classify_announcement(title: str) -> tuple[str, str]:
    """Classify disclosure titles by topic and attention level, not sentiment."""
    text = str(title)
    if any(
        keyword in text
        for keyword in ("退市", "立案", "处罚", "风险提示", "重大诉讼")
    ):
        return "监管与风险", "高"
    if any(keyword in text for keyword in ("年度报告", "季度报告", "半年报")):
        return "财务报告", "高"
    if any(keyword in text for keyword in ("业绩预告", "业绩快报")):
        return "业绩动态", "高"
    if any(keyword in text for keyword in ("回购", "分红", "权益分派")):
        return "分红与回购", "中"
    if any(keyword in text for keyword in ("增持", "减持", "股权变动")):
        return "股权与资本", "中"
    if any(keyword in text for keyword in ("董事", "监事", "高管", "治理")):
        return "公司治理", "中"
    if any(keyword in text for keyword in ("合同", "项目", "投资", "并购")):
        return "经营动态", "中"
    return "其他公告", "低"


def is_allowed_disclosure_url(url: str) -> bool:
    """Allow links only from known mainland disclosure domains."""
    parsed = urlparse(str(url).strip())
    hostname = (parsed.hostname or "").lower()
    allowed_hosts = (
        "cninfo.com.cn",
        "sse.com.cn",
        "szse.cn",
        "bse.cn",
    )
    return parsed.scheme in {"http", "https"} and any(
        hostname == host or hostname.endswith(f".{host}")
        for host in allowed_hosts
    )


def build_cninfo_pdf_url(announcement_url: str) -> str:
    """Convert one validated CNINFO detail link to its official static PDF."""
    clean_url = str(announcement_url).strip()
    if not is_allowed_disclosure_url(clean_url):
        raise ValueError("年度报告链接不是受信任的官方披露地址。")

    parsed = urlparse(clean_url)
    hostname = (parsed.hostname or "").lower()
    if not (
        hostname == "cninfo.com.cn"
        or hostname.endswith(".cninfo.com.cn")
    ):
        raise ValueError("自动载入目前只支持巨潮资讯年度报告。")

    if parsed.path.lower().endswith(".pdf"):
        return clean_url
    if parsed.path.rstrip("/") == "/new/announcement/download":
        return clean_url

    query = parse_qs(parsed.query)
    announcement_ids = query.get("announcementId", [])
    announcement_times = query.get("announcementTime", [])
    if not announcement_ids or not announcement_times:
        raise ValueError("官方公告链接缺少报告下载标识。")

    announcement_id = str(announcement_ids[0]).strip()
    announcement_time = str(announcement_times[0]).strip()[:10]
    if not re.fullmatch(r"\d{8,20}", announcement_id):
        raise ValueError("官方公告编号格式无效。")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", announcement_time):
        raise ValueError("官方公告日期格式无效。")

    return (
        "https://static.cninfo.com.cn/finalpage/"
        f"{announcement_time}/{announcement_id}.PDF"
    )


def download_official_pdf(
    announcement_url: str,
    *,
    max_bytes: int = 80 * 1024 * 1024,
) -> bytes:
    """Download a bounded, signature-checked PDF from an official source."""
    if max_bytes <= 0:
        raise ValueError("下载大小上限必须大于0。")
    pdf_url = build_cninfo_pdf_url(announcement_url)
    request = Request(
        pdf_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; WFZ-Financial-Research/1.0)"
            ),
            "Referer": "https://www.cninfo.com.cn/",
        },
    )
    try:
        with urlopen(request, timeout=35) as response:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > max_bytes:
                raise DataSourceError(
                    "该年度报告超过自动载入大小上限，请使用官方链接手工上传。"
                )
            content = response.read(max_bytes + 1)
    except DataSourceError:
        raise
    except Exception as error:
        raise DataSourceError(
            "官方年度报告暂时无法自动载入，请使用原文链接或手工上传。"
        ) from error

    if len(content) > max_bytes:
        raise DataSourceError(
            "该年度报告超过自动载入大小上限，请使用官方链接手工上传。"
        )
    if not content.startswith(b"%PDF"):
        raise DataSourceError(
            "官方地址没有返回有效PDF，系统已停止分析以避免使用错误文件。"
        )
    return content


def prepare_announcements(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalise official announcements and reject untrusted links."""
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "code",
                "name",
                "title",
                "date",
                "url",
                "category",
                "attention",
            ]
        )

    aliases = {
        "代码": "code",
        "简称": "name",
        "公告标题": "title",
        "公告时间": "date",
        "公告链接": "url",
    }
    renamed = frame.rename(columns=aliases)
    required = {"code", "name", "title", "date", "url"}
    if not required.issubset(renamed.columns):
        raise ValueError("公告数据缺少必要字段。")

    result = renamed.loc[:, ["code", "name", "title", "date", "url"]].copy()
    result["code"] = result["code"].astype(str).str.extract(
        r"(\d{6})",
        expand=False,
    )
    result["title"] = result["title"].astype(str).str.strip()
    result["url"] = result["url"].astype(str).str.strip()
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    result = result.loc[result["url"].map(is_allowed_disclosure_url)]
    result = result.dropna(subset=["code", "title", "date"])

    classifications = result["title"].map(classify_announcement)
    result["category"] = classifications.map(lambda item: item[0])
    result["attention"] = classifications.map(lambda item: item[1])
    result = result.sort_values("date", ascending=False).drop_duplicates(
        subset=["title", "date"],
        keep="first",
    )
    result["date"] = result["date"].dt.date
    return result.reset_index(drop=True)


def select_latest_annual_report(
    announcements: pd.DataFrame,
) -> pd.Series | None:
    """Return the latest complete report, preferring Chinese over translations."""
    prepared = prepare_announcements(announcements)
    if prepared.empty:
        return None
    titles = prepared["title"]
    mask = titles.str.contains("年度报告", na=False) & ~titles.str.contains(
        "半年度报告|摘要|取消|问询|回复",
        regex=True,
        na=False,
    )
    candidates = prepared.loc[mask]
    if candidates.empty:
        return None

    # A translated edition can be published after the Chinese original.
    # Compare report years first so a prior-year Chinese report never wins,
    # then prefer the Chinese original within the latest reporting year.
    report_years = pd.to_numeric(
        candidates["title"].str.extract(
            r"((?:19|20)\d{2})年年度报告",
            expand=False,
        ),
        errors="coerce",
    )
    if report_years.notna().any():
        latest_report_year = report_years.max()
        candidates = candidates.loc[report_years == latest_report_year]

    translated_mask = candidates["title"].str.contains(
        r"英文(?:版|译本)?|English",
        case=False,
        regex=True,
        na=False,
    )
    chinese_originals = candidates.loc[~translated_mask]
    if not chinese_originals.empty:
        return chinese_originals.iloc[0]
    return candidates.iloc[0]


def fetch_company_directory() -> pd.DataFrame:
    """Fetch the current A-share company directory through AKShare."""
    try:
        import akshare as ak

        frame = ak.stock_info_a_code_name()
        return prepare_company_directory(frame)
    except Exception as error:  # provider errors vary by upstream source
        raise DataSourceError(
            "当前无法读取A股公司目录，请稍后重试或直接输入6位股票代码。"
        ) from error


def fetch_market_history(
    code: str,
    start_date: date,
    end_date: date,
    *,
    adjust: str = "qfq",
) -> pd.DataFrame:
    """Fetch daily A-share OHLCV history through the provider adapter."""
    if adjust not in {"", "qfq", "hfq"}:
        raise ValueError("复权方式必须是不复权、前复权或后复权。")
    company = build_company_identity(code)
    try:
        import akshare as ak
    except Exception as error:
        raise DataSourceError("行情数据组件当前不可用，请稍后重试。") from error

    # Keep every public request bounded on the small Render instance.  Tencent
    # is the quick price source, but its daily adapter currently exposes only
    # six columns and therefore no ordinary turnover.  When needed, request the
    # same bounded date window from Eastmoney and retain only date + turnover;
    # never start the old Sina full-history decode.
    provider_timeout_seconds = 6.0
    symbol = f"{company['exchange'].lower()}{code}"
    fast_source_error: Exception | None = None
    try:
        fast_frame = ak.stock_zh_a_hist_tx(
            symbol=symbol,
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
            adjust=adjust,
            timeout=provider_timeout_seconds,
        )
        prepared = prepare_tencent_market_history(fast_frame)
        if prepared.empty:
            raise ValueError("腾讯财经返回了空行情。")
    except Exception as error:
        fast_source_error = error
    else:
        prepared.attrs["source"] = "腾讯财经公开日线（快速源）"
        if prepared["turnover"].notna().any():
            prepared.attrs["turnover_source"] = (
                "腾讯财经公开日线直接字段"
            )
            return prepared

        try:
            turnover_frame = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"),
                adjust=adjust,
                timeout=provider_timeout_seconds,
            )
            prepared = merge_direct_turnover_history(
                prepared,
                turnover_frame,
                source_label=(
                    "东方财富公开日线直接字段（与腾讯价格按日期合并）"
                ),
            )
        except Exception:
            # Turnover is an enhancement, not a reason to discard valid price
            # history.  The UI will state the limitation instead of guessing.
            prepared.attrs["turnover_source"] = "暂未取得"
        else:
            if not prepared["turnover"].notna().any():
                prepared.attrs["turnover_source"] = "暂未取得"
        return prepared

    try:
        fallback_frame = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
            adjust=adjust,
            timeout=provider_timeout_seconds,
        )
        prepared = prepare_market_history(fallback_frame)
        if prepared.empty:
            raise ValueError("东方财富返回了空行情。")
        prepared.attrs["source"] = "东方财富公开日线（备用源）"
        prepared.attrs["turnover_source"] = (
            "东方财富公开日线直接字段"
        )
        return prepared
    except Exception as fallback_error:
        raise DataSourceError(
            "当前无法从两个公开来源取得该公司的历史日线，请稍后重试。"
        ) from ExceptionGroup(
            "公开行情快速源和备用源均不可用",
            [fast_source_error, fallback_error],
        )


def _read_cninfo_json(request: Request) -> dict[str, object]:
    """Read one bounded CNINFO JSON response using only the standard library."""
    with urlopen(
        request,
        timeout=CNINFO_REQUEST_TIMEOUT_SECONDS,
    ) as response:
        content = response.read(CNINFO_MAX_RESPONSE_BYTES + 1)
    if len(content) > CNINFO_MAX_RESPONSE_BYTES:
        raise ValueError("巨潮资讯单次响应超过安全大小上限。")
    decoded = json.loads(content.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("巨潮资讯返回了无法识别的数据结构。")
    return decoded


def _cninfo_headers() -> dict[str, str]:
    return {
        "Accept": "application/json, text/plain, */*",
        "Referer": (
            "https://www.cninfo.com.cn/new/commonUrl/pageOfSearch?"
            "url=disclosure/list/search"
        ),
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
        ),
    }


@lru_cache(maxsize=1)
def _load_cninfo_stock_ids() -> dict[str, str]:
    """Load and reuse the official A-share code-to-organisation mapping."""
    request = Request(
        CNINFO_STOCK_DIRECTORY_URL,
        headers=_cninfo_headers(),
    )
    decoded = _read_cninfo_json(request)
    stock_list = decoded.get("stockList")
    if not isinstance(stock_list, list):
        raise ValueError("巨潮资讯公司目录缺少股票列表。")

    result: dict[str, str] = {}
    for item in stock_list:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code", "")).strip()
        organisation_id = str(item.get("orgId", "")).strip()
        if re.fullmatch(r"\d{6}", code) and organisation_id:
            result[code] = organisation_id
    if not result:
        raise ValueError("巨潮资讯公司目录没有可用记录。")
    return result


def _fetch_cninfo_announcement_page(
    base_payload: dict[str, str],
    page_number: int,
) -> dict[str, object]:
    payload = dict(base_payload)
    payload["pageNum"] = str(page_number)
    request = Request(
        CNINFO_ANNOUNCEMENT_QUERY_URL,
        data=urlencode(payload).encode("utf-8"),
        headers={
            **_cninfo_headers(),
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://www.cninfo.com.cn",
        },
        method="POST",
    )
    return _read_cninfo_json(request)


def _cninfo_rows_to_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    """Convert CNINFO response rows into the app's trusted schema."""
    if not rows:
        return prepare_announcements(pd.DataFrame())

    raw = pd.DataFrame(rows)
    required = {
        "secCode",
        "secName",
        "announcementTitle",
        "announcementTime",
        "announcementId",
        "orgId",
    }
    if not required.issubset(raw.columns):
        raise ValueError("巨潮资讯公告响应缺少必要字段。")

    dates = pd.to_datetime(
        raw["announcementTime"],
        unit="ms",
        utc=True,
        errors="coerce",
    ).dt.tz_convert("Asia/Shanghai").dt.tz_localize(None)
    announcement_times = dates.dt.strftime("%Y-%m-%d %H:%M:%S")
    detail_urls: list[str] = []
    for code, announcement_id, organisation_id, published_at in zip(
        raw["secCode"],
        raw["announcementId"],
        raw["orgId"],
        announcement_times,
    ):
        query = urlencode(
            {
                "stockCode": str(code),
                "announcementId": str(announcement_id),
                "orgId": str(organisation_id),
                "announcementTime": str(published_at),
            }
        )
        detail_urls.append(
            f"https://www.cninfo.com.cn/new/disclosure/detail?{query}"
        )

    normalised = pd.DataFrame(
        {
            "代码": raw["secCode"],
            "简称": raw["secName"],
            "公告标题": raw["announcementTitle"],
            "公告时间": dates,
            "公告链接": detail_urls,
        }
    )
    return prepare_announcements(normalised)


def fetch_announcements(
    code: str,
    start_date: date,
    end_date: date,
    *,
    category: str = "",
) -> pd.DataFrame:
    """Fetch official disclosures with bounded requests and page fan-out."""
    build_company_identity(code)
    if end_date < start_date:
        raise ValueError("公告查询结束日期不能早于开始日期。")
    if category and category not in CNINFO_CATEGORY_CODES:
        raise ValueError("暂不支持该公告类别。")

    try:
        organisation_id = _load_cninfo_stock_ids().get(code)
        if not organisation_id:
            raise ValueError("巨潮资讯公司目录中没有该股票代码。")
        base_payload = {
            "pageNum": "1",
            "pageSize": str(CNINFO_PAGE_SIZE),
            "column": "szse",
            "tabName": "fulltext",
            "plate": "",
            "stock": f"{code},{organisation_id}",
            "searchkey": "",
            "secid": "",
            "category": CNINFO_CATEGORY_CODES.get(category, ""),
            "trade": "",
            "seDate": (
                f"{start_date.isoformat()}~{end_date.isoformat()}"
            ),
            "sortName": "",
            "sortType": "",
            "isHLtitle": "true",
        }
        first_page = _fetch_cninfo_announcement_page(base_payload, 1)
        total = int(first_page.get("totalAnnouncement", 0) or 0)
        if total < 0:
            raise ValueError("巨潮资讯返回了无效公告数量。")
        page_count = math.ceil(total / CNINFO_PAGE_SIZE)
        if page_count > CNINFO_MAX_PAGES:
            raise ValueError(
                "公告数量超过一次安全读取上限，请缩短日期范围或选择公告类别。"
            )

        first_rows = first_page.get("announcements") or []
        if not isinstance(first_rows, list):
            raise ValueError("巨潮资讯返回了无法识别的公告列表。")
        rows_by_page: dict[int, list[dict[str, object]]] = {
            1: [item for item in first_rows if isinstance(item, dict)]
        }
        remaining_pages = range(2, page_count + 1)
        if page_count > 1:
            with ThreadPoolExecutor(
                max_workers=min(CNINFO_MAX_WORKERS, page_count - 1),
                thread_name_prefix="wfz-cninfo",
            ) as executor:
                futures = {
                    page_number: executor.submit(
                        _fetch_cninfo_announcement_page,
                        base_payload,
                        page_number,
                    )
                    for page_number in remaining_pages
                }
                for page_number, future in futures.items():
                    decoded = future.result()
                    page_rows = decoded.get("announcements") or []
                    if not isinstance(page_rows, list):
                        raise ValueError(
                            "巨潮资讯返回了无法识别的公告列表。"
                        )
                    rows_by_page[page_number] = [
                        item for item in page_rows if isinstance(item, dict)
                    ]

        rows = [
            row
            for page_number in sorted(rows_by_page)
            for row in rows_by_page[page_number]
        ]
        prepared = _cninfo_rows_to_frame(rows)
        prepared.attrs["source"] = "巨潮资讯官方披露（限时读取）"
        prepared.attrs["retrieved_pages"] = page_count
        prepared.attrs["total_announcements"] = total
        return prepared
    except ValueError as error:
        raise DataSourceError(
            f"当前无法取得巨潮资讯公告：{error}"
        ) from error
    except Exception as error:
        raise DataSourceError(
            "当前无法取得巨潮资讯公告，请稍后重试。"
        ) from error
