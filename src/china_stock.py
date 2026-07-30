"""Validated helpers for Chinese listed-company research.

The external data provider is intentionally kept behind a small set of
functions.  Financial and market calculations remain deterministic Python
logic, while the interface can fall back gracefully if a public source is
temporarily unavailable.
"""

from __future__ import annotations

import math
import re
from datetime import date
from typing import TypedDict
from urllib.parse import parse_qs, urlparse
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
    turnover: float | None
    turnover_status: str
    effective_turnover: float | None
    effective_turnover_status: str
    limit_up_reference: float
    limit_up_status: str
    limit_up_note: str


class DataSourceError(RuntimeError):
    """Raised when a public market-data source cannot be used safely."""


EXCHANGE_NAMES = {
    "SH": "上海证券交易所",
    "SZ": "深圳证券交易所",
    "BJ": "北京证券交易所",
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
    if frame.empty:
        return pd.DataFrame(
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
    return result.loc[
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

    turnover_value = latest["turnover"]
    turnover = (
        None if pd.isna(turnover_value) else float(turnover_value) / 100
    )
    turnover_status = (
        "公开日线已提供普通换手率"
        if turnover is not None
        else "当前公开日线未提供换手率"
    )

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
        "turnover": turnover,
        "turnover_status": turnover_status,
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
    """Return the latest complete annual report, excluding summaries."""
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

    try:
        frame = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
            adjust=adjust,
        )
        prepared = prepare_market_history(frame)
        if prepared.empty:
            raise ValueError("东方财富返回了空行情。")
        prepared.attrs["source"] = "东方财富公开日线"
        return prepared
    except Exception as primary_error:
        try:
            symbol = f"{company['exchange'].lower()}{code}"
            fallback_frame = ak.stock_zh_a_hist_tx(
                symbol=symbol,
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"),
                adjust=adjust,
            )
            prepared = prepare_tencent_market_history(fallback_frame)
            if prepared.empty:
                raise ValueError("腾讯财经返回了空行情。")
            prepared.attrs["source"] = "腾讯财经公开日线（备用源）"
            return prepared
        except Exception as fallback_error:
            raise DataSourceError(
                "当前无法从两个公开来源取得该公司的历史日线，请稍后重试。"
            ) from ExceptionGroup(
                "公开行情主源和备用源均不可用",
                [primary_error, fallback_error],
            )


def fetch_announcements(
    code: str,
    start_date: date,
    end_date: date,
    *,
    category: str = "",
) -> pd.DataFrame:
    """Fetch official CNINFO disclosures for one mainland listed company."""
    build_company_identity(code)
    try:
        import akshare as ak

        frame = ak.stock_zh_a_disclosure_report_cninfo(
            symbol=code,
            market="沪深京",
            keyword="",
            category=category,
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
        )
        return prepare_announcements(frame)
    except Exception as error:
        raise DataSourceError(
            "当前无法取得巨潮资讯公告，请稍后重试。"
        ) from error
