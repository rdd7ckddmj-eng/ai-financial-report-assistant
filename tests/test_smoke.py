from datetime import date

import pandas as pd


def test_project_smoke() -> None:
    assert 1 + 1 == 2


def test_event_evidence_chain_renderer_shows_auditable_limits() -> None:
    """Render the evidence chain as real Streamlit components."""
    from streamlit.testing.v1 import AppTest

    script = """
from src.app import _show_event_evidence_chain

chain = {
    "event_date": "2026-07-20",
    "window_days": 7,
    "status": "matched",
    "matches": [{
        "source_id": "official-1",
        "title": "贵州茅台重大事项公告",
        "published_date": "2026-07-18",
        "source_type": "其他公告",
        "source_url": "https://static.cninfo.com.cn/example.pdf",
        "evidence_grade": "A",
        "days_before_event": 2,
        "relation": "此前2天公开",
    }],
    "matched_count": 1,
    "same_day_count": 0,
    "nearest_gap_days": 2,
    "future_excluded_count": 4,
    "conclusion": (
        "所选日期此前 6 天内匹配 1 条官方公告；"
        "最近一条相隔 2 天。"
    ),
    "limitation": (
        "公告与异常交易日时间接近，只能作为复盘线索，"
        "不能据此认定公告导致了价格或成交量变化。"
    ),
}
_show_event_evidence_chain(chain, event_context="明显放量")
"""
    app_test = AppTest.from_string(script).run()

    assert not app_test.exception
    assert any(
        "异动—公告证据链" in item.value for item in app_test.markdown
    )
    assert any(
        "异动类型：明显放量" in item.value for item in app_test.caption
    )
    assert any(
        "最近一条相隔 2 天" in item.value for item in app_test.success
    )
    assert any(
        "不能据此认定" in item.value for item in app_test.warning
    )
    assert any(
        "截止日后公告未进入" in item.value for item in app_test.caption
    )


def test_company_research_page_renders_a_successful_market_result(
    monkeypatch,
) -> None:
    """Keep the deployed success branch covered, including source provenance."""
    from src import app

    company = {
        "code": "600519",
        "name": "贵州茅台",
        "exchange": "SH",
        "exchange_name": "上海证券交易所",
        "canonical_code": "600519.SH",
    }
    market_frame = pd.DataFrame(
        {
            "date": [pd.Timestamp("2026-07-29")],
            "open": [1300.0],
            "high": [1325.0],
            "low": [1295.0],
            "close": [1321.0],
            "volume": [1000.0],
            "amount": [1_321_000.0],
        }
    )
    market_frame.attrs["source"] = "腾讯财经公开日线（备用源）"
    metrics = {
        "latest_date": "2026-07-29",
        "latest_close": 1321.0,
        "daily_change": 0.001,
        "return_20d": 0.107,
        "return_60d": 0.08,
        "return_250d": None,
        "annualised_volatility": 0.214,
        "max_drawdown": -0.25,
        "observations": 1,
    }

    monkeypatch.setattr(app, "apply_product_theme", lambda: None)
    monkeypatch.setattr(app, "show_compact_page_header", lambda *args: None)
    monkeypatch.setattr(app, "_selected_company", lambda: company)
    monkeypatch.setattr(app, "_show_company_banner", lambda selected: None)
    monkeypatch.setattr(
        app,
        "_load_company_research_data",
        lambda selected: (market_frame, metrics, None),
    )
    monkeypatch.setattr(app, "show_product_footer", lambda: None)

    app.render_company_research_page()


def test_market_page_passes_activity_evidence_to_the_renderer(
    monkeypatch,
) -> None:
    """Cover the K-line page integration without calling a live data source."""
    from src import app

    company = {
        "code": "600519",
        "name": "贵州茅台",
        "exchange": "SH",
        "exchange_name": "上海证券交易所",
        "canonical_code": "600519.SH",
    }
    dates = pd.date_range("2026-06-01", periods=30, freq="B")
    close = pd.Series([100 + index * 0.2 for index in range(len(dates))])
    market_frame = pd.DataFrame(
        {
            "date": dates,
            "open": close - 0.2,
            "high": close + 0.6,
            "low": close - 0.8,
            "close": close,
            "volume": [1_000_000] * 29 + [2_000_000],
            "amount": 100_000_000,
            "turnover": 2.5,
        }
    )
    market_frame.attrs["source"] = "测试公开行情"
    rendered_activity = []
    rendered_events = []

    monkeypatch.setattr(app, "apply_product_theme", lambda: None)
    monkeypatch.setattr(app, "show_compact_page_header", lambda *args: None)
    monkeypatch.setattr(app, "_selected_company", lambda: company)
    monkeypatch.setattr(app, "_show_company_banner", lambda selected: None)
    monkeypatch.setattr(
        app,
        "load_a_share_history",
        lambda *args: market_frame,
    )
    monkeypatch.setattr(
        app,
        "_show_market_activity_evidence",
        lambda activity: rendered_activity.append(activity),
    )
    monkeypatch.setattr(
        app,
        "_show_activity_event_replay",
        lambda events, selected: rendered_events.extend(events),
    )
    monkeypatch.setattr(app, "_build_kline_figure", lambda *args: object())
    monkeypatch.setattr(app.st, "plotly_chart", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "show_product_footer", lambda: None)

    app.render_market_page()

    assert rendered_activity[0]["volume_ratio_20d"] == 2
    assert rendered_activity[0]["effective_turnover"] is None
    assert rendered_events[0]["event_type"] == "明显放量"


def test_historical_lens_page_renders_a_point_in_time_snapshot(
    monkeypatch,
) -> None:
    """Keep the new time-isolated page covered without calling live sources."""
    from src import app

    company = {
        "code": "600519",
        "name": "贵州茅台",
        "exchange": "SH",
        "exchange_name": "上海证券交易所",
        "canonical_code": "600519.SH",
    }
    dates = pd.date_range("2024-01-02", periods=700, freq="B")
    close = pd.Series([1000 + index * 0.5 for index in range(len(dates))])
    market_frame = pd.DataFrame(
        {
            "date": dates,
            "open": close - 1,
            "high": close + 3,
            "low": close - 3,
            "close": close,
            "volume": 1_000_000,
            "amount": 1_000_000_000,
            "turnover": 1.5,
        }
    )
    market_frame.attrs["source"] = "测试公开行情"
    announcements = pd.DataFrame(
        {
            "date": [date.today()],
            "title": ["测试官方公告"],
            "url": ["https://static.cninfo.com.cn/test.pdf"],
            "category": ["其他公告"],
            "attention": ["低"],
        }
    )

    monkeypatch.setattr(app, "apply_product_theme", lambda: None)
    monkeypatch.setattr(app, "show_compact_page_header", lambda *args: None)
    monkeypatch.setattr(app, "_selected_company", lambda: company)
    monkeypatch.setattr(app, "_show_company_banner", lambda selected: None)
    monkeypatch.setattr(
        app,
        "load_a_share_history",
        lambda *args: market_frame,
    )
    monkeypatch.setattr(
        app,
        "load_company_announcements",
        lambda *args: announcements,
    )
    monkeypatch.setattr(
        app,
        "_build_kline_figure",
        lambda *args: object(),
    )
    monkeypatch.setattr(app.st, "plotly_chart", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        app,
        "select_latest_annual_report",
        lambda frame: None,
    )
    monkeypatch.setattr(app, "show_product_footer", lambda: None)

    app.render_historical_lens_page()
