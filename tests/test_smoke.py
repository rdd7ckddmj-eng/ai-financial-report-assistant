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
