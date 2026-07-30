from datetime import date

import pandas as pd


def test_project_smoke() -> None:
    assert 1 + 1 == 2


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
