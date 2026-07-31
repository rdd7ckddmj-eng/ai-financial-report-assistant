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
    link_buttons = app_test.get("link_button")
    assert len(link_buttons) == 1
    assert link_buttons[0].proto.label == "查看原文 ↗"
    assert link_buttons[0].proto.url == (
        "https://static.cninfo.com.cn/example.pdf"
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
    monkeypatch.setattr(app, "_build_kline_figure", lambda *args: object())
    monkeypatch.setattr(app.st, "plotly_chart", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "show_product_footer", lambda: None)

    app.render_market_page()

    assert rendered_activity[0]["volume_ratio_20d"] == 2
    assert rendered_activity[0]["effective_turnover"] is None


def test_volume_turnover_page_builds_a_bounded_research_snapshot(
    monkeypatch,
) -> None:
    """Cover the dedicated participation page without live providers."""
    from src import app

    company = {
        "code": "600519",
        "name": "贵州茅台",
        "exchange": "SH",
        "exchange_name": "上海证券交易所",
        "canonical_code": "600519.SH",
    }
    dates = pd.date_range("2026-04-01", periods=60, freq="B")
    close = pd.Series([100 + index * 0.1 for index in range(len(dates))])
    market_frame = pd.DataFrame(
        {
            "date": dates,
            "open": close - 0.2,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": [1_000_000.0] * 59 + [2_500_000.0],
            "amount": 100_000_000.0,
            "turnover": [1.0] * 59 + [4.0],
        }
    )
    market_frame.attrs["source"] = "测试公开行情"
    verified_snapshots = []

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
        "_build_volume_turnover_figure",
        lambda *args: object(),
    )
    monkeypatch.setattr(app.st, "plotly_chart", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        app,
        "_show_effective_turnover_verification",
        lambda snapshot: verified_snapshots.append(snapshot),
    )
    monkeypatch.setattr(app, "show_product_footer", lambda: None)

    app.render_volume_turnover_page()

    assert verified_snapshots[0]["volume_ratio_20d"] == 2.5
    assert verified_snapshots[0]["ordinary_turnover"] == 0.04
    assert verified_snapshots[0]["high_volume_days"] == 1


def test_market_radar_page_scans_and_ranks_a_bounded_watchlist(
    monkeypatch,
) -> None:
    """Cover the research queue without calling live market providers."""
    from src import app

    downloads = []
    dates = pd.date_range("2026-05-01", periods=30, freq="B")
    close = pd.Series([100 + index * 0.1 for index in range(len(dates))])

    def fake_history(
        code: str,
        start_date_text: str,
        end_date_text: str,
        adjust: str,
    ) -> pd.DataFrame:
        volume = [1_000_000.0] * len(dates)
        turnover = [1.0] * len(dates)
        if code == "600519":
            volume[-1] = 2_500_000.0
            turnover[-1] = 4.0
        frame = pd.DataFrame(
            {
                "date": dates,
                "open": close - 0.2,
                "high": close + 0.6,
                "low": close - 0.8,
                "close": close,
                "volume": volume,
                "amount": 100_000_000.0,
                "turnover": turnover,
            }
        )
        frame.attrs["source"] = "测试公开行情"
        frame.attrs["turnover_source"] = "测试换手率"
        return frame

    monkeypatch.setattr(app, "apply_product_theme", lambda: None)
    monkeypatch.setattr(app, "show_compact_page_header", lambda *args: None)
    monkeypatch.setattr(app, "show_product_footer", lambda: None)
    monkeypatch.setattr(
        app,
        "load_a_share_directory",
        lambda: pd.DataFrame(
            {
                "code": ["600519", "300750"],
                "name": ["贵州茅台", "宁德时代"],
            }
        ),
    )
    monkeypatch.setattr(app, "load_a_share_history", fake_history)
    monkeypatch.setattr(
        app,
        "load_company_announcements",
        lambda code, *args, **kwargs: (
            pd.DataFrame(
                {
                    "code": ["600519"],
                    "name": ["贵州茅台"],
                    "title": ["贵州茅台2025年年度报告"],
                    "date": [date(2026, 7, 30)],
                    "url": [
                        "https://static.cninfo.com.cn/finalpage/"
                        "2026-07-30/1234567890.PDF"
                    ],
                    "category": ["财务报告"],
                    "attention": ["高"],
                }
            )
            if code == "600519"
            else pd.DataFrame(
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
        ),
    )
    monkeypatch.setattr(
        app.st,
        "text_area",
        lambda *args, **kwargs: "600519, 300750",
    )
    monkeypatch.setattr(
        app.st,
        "form_submit_button",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        app.st,
        "download_button",
        lambda label, **kwargs: downloads.append((label, kwargs)),
    )
    app.st.session_state.pop("market_radar_rows", None)
    app.st.session_state.pop("market_radar_failures", None)

    app.render_market_radar_page()

    rows = app.st.session_state["market_radar_rows"]
    assert len(rows) == 2
    assert rows[0]["company"]["code"] == "600519"
    assert rows[0]["triggered_signals"] == [
        "明显放量",
        "普通换手率历史高位",
    ]
    assert rows[0]["research_priority"] == "P1｜立即核查"
    assert rows[0]["latest_disclosure"]["title"] == (
        "贵州茅台2025年年度报告"
    )
    assert app.st.session_state["market_radar_failures"] == []
    assert downloads[0][0] == "下载自选股研究任务简报（HTML）"
    assert downloads[0][1]["mime"] == "text/html"
    assert b"WFZ" in downloads[0][1]["data"]


def test_limit_up_board_page_builds_daily_wall(monkeypatch) -> None:
    """Cover the new daily wall without calling the public provider."""
    from src import app

    pool_frame = pd.DataFrame(
        {
            "代码": ["600519", "300750"],
            "名称": ["贵州茅台", "宁德时代"],
            "涨跌幅": [10.0, 20.0],
            "最新价": [1321.0, 310.0],
            "成交额": [4_500_000_000, 6_000_000_000],
            "流通市值": [1_600_000_000_000, 1_200_000_000_000],
            "总市值": [1_700_000_000_000, 1_300_000_000_000],
            "换手率": [1.5, 4.5],
            "封板资金": [500_000_000, 300_000_000],
            "首次封板时间": [100501, 94530],
            "最后封板时间": [100501, 145000],
            "炸板次数": [0, 0],
            "涨停统计": ["2/2", "1/1"],
            "连板数": [2, 1],
            "所属行业": ["酿酒行业", "电池"],
        }
    )

    monkeypatch.setattr(app, "apply_product_theme", lambda: None)
    monkeypatch.setattr(app, "show_compact_page_header", lambda *args: None)
    monkeypatch.setattr(app, "show_product_footer", lambda: None)
    monkeypatch.setattr(app, "load_limit_up_pool", lambda *args: pool_frame)
    monkeypatch.setattr(
        app.st,
        "date_input",
        lambda *args, **kwargs: date(2026, 7, 30),
    )
    monkeypatch.setattr(
        app.st,
        "form_submit_button",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        app.st,
        "dataframe",
        lambda *args, **kwargs: None,
    )
    app.st.session_state.pop("limit_up_board_snapshot", None)

    app.render_limit_up_board_page()

    snapshot = app.st.session_state["limit_up_board_snapshot"]
    assert snapshot["total_count"] == 2
    assert snapshot["consecutive_board_count"] == 1
    assert snapshot["rows"][0]["code"] == "600519"
    assert snapshot["rows"][0]["first_limit_time"] == "10:05:01"
    assert snapshot["review"]["ladder"] == [
        {"boards": 2, "company_count": 1, "share": 0.5},
        {"boards": 1, "company_count": 1, "share": 0.5},
    ]
    assert snapshot["review"]["early_seal_count"] == 1
    assert snapshot["review"]["resealed_count"] == 0


def test_market_anomaly_page_builds_report_and_evidence_chain(
    monkeypatch,
) -> None:
    """Cover the dedicated Agent page without calling live data sources."""
    from src import app

    company = {
        "code": "600519",
        "name": "贵州茅台",
        "exchange": "SH",
        "exchange_name": "上海证券交易所",
        "canonical_code": "600519.SH",
    }
    dates = pd.date_range("2025-01-02", periods=300, freq="B")
    close = pd.Series([100 + index * 0.1 for index in range(len(dates))])
    market_frame = pd.DataFrame(
        {
            "date": dates,
            "open": close - 0.2,
            "high": close + 0.6,
            "low": close - 0.8,
            "close": close,
            "volume": [1_000_000] * 299 + [2_500_000],
            "amount": 100_000_000,
            "turnover": [1.0] * 299 + [4.0],
        }
    )
    market_frame.attrs["source"] = "测试公开行情"
    announcements = pd.DataFrame(
        {
            "date": [dates[-1].date()],
            "title": ["测试官方公告"],
            "url": ["https://static.cninfo.com.cn/test.pdf"],
            "category": ["其他公告"],
            "attention": ["低"],
        }
    )
    rendered_reports = []
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
        "load_company_announcements",
        lambda *args: announcements,
    )
    monkeypatch.setattr(
        app,
        "_show_market_anomaly_report",
        lambda report: rendered_reports.append(report),
    )
    monkeypatch.setattr(
        app,
        "_show_market_activity_evidence",
        lambda activity: None,
    )
    monkeypatch.setattr(
        app,
        "_show_anomaly_event_research",
        lambda events, selected, disclosures, **kwargs: rendered_events.extend(
            events
        ),
    )
    monkeypatch.setattr(app, "show_product_footer", lambda: None)

    app.render_market_anomaly_page()

    assert rendered_reports[0]["status"] == "compound_anomaly"
    assert rendered_reports[0]["triggered_signal_count"] == 2
    assert rendered_events[0]["event_type"] == (
        "明显放量 + 普通换手率高位"
    )


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


def test_financial_trend_page_renders_verified_flagship(
    monkeypatch,
) -> None:
    """Keep the standalone audited trend page independent of live sources."""
    from src import app

    company = {
        "code": "600519",
        "name": "贵州茅台",
        "exchange": "SH",
        "exchange_name": "上海证券交易所",
        "canonical_code": "600519.SH",
    }
    rendered_history = []

    monkeypatch.setattr(app, "apply_product_theme", lambda: None)
    monkeypatch.setattr(app, "show_compact_page_header", lambda *args: None)
    monkeypatch.setattr(app, "_selected_company", lambda: company)
    monkeypatch.setattr(app, "_show_company_banner", lambda selected: None)
    monkeypatch.setattr(
        app,
        "_show_verified_financial_history",
        lambda selected, cutoff: rendered_history.append(
            (selected, cutoff)
        ),
    )
    monkeypatch.setattr(app, "show_product_footer", lambda: None)

    app.render_financial_trend_page()

    assert rendered_history
    assert rendered_history[0][0]["code"] == "600519"


def test_financial_trend_page_renders_verified_catl(
    monkeypatch,
) -> None:
    """Keep the second audited company independent of live sources."""
    from src import app

    company = {
        "code": "300750",
        "name": "宁德时代",
        "exchange": "SZ",
        "exchange_name": "深圳证券交易所",
        "canonical_code": "300750.SZ",
    }
    rendered_history = []

    monkeypatch.setattr(app, "apply_product_theme", lambda: None)
    monkeypatch.setattr(app, "show_compact_page_header", lambda *args: None)
    monkeypatch.setattr(app, "_selected_company", lambda: company)
    monkeypatch.setattr(app, "_show_company_banner", lambda selected: None)
    monkeypatch.setattr(
        app,
        "_show_verified_financial_history",
        lambda selected, cutoff: rendered_history.append(
            (selected, cutoff)
        ),
    )
    monkeypatch.setattr(app, "show_product_footer", lambda: None)

    app.render_financial_trend_page()

    assert rendered_history
    assert rendered_history[0][0]["code"] == "300750"


def test_financial_trend_page_shows_catl_evidence_in_streamlit() -> None:
    """Render the real page controls, metrics, and official report links."""
    from streamlit.testing.v1 import AppTest

    script = """
from src import app

company = app.resolve_company("300750")[0]
app._selected_company = lambda: company
app._show_company_banner = lambda selected: None
app.render_financial_trend_page()
"""
    app_test = AppTest.from_string(script).run()
    visible_text = "\n".join(
        str(item.value)
        for group in (
            app_test.title,
            app_test.info,
            app_test.success,
            app_test.warning,
            app_test.caption,
            app_test.markdown,
        )
        for item in group
    )

    assert not app_test.exception
    assert "宁德时代" in visible_text
    assert "标准化接入检查通过" in visible_text
    assert "收入与利润方向不一致" in visible_text
    assert len(app_test.metric) == 12
    assert len(app_test.get("link_button")) == 3
    assert app_test.selectbox[0].value == "宁德时代｜300750.SZ"


def test_financial_trend_page_shows_byd_evidence_in_streamlit() -> None:
    """Prove the third catalogue company appears without page-code edits."""
    from streamlit.testing.v1 import AppTest

    script = """
from src import app

company = {
    "code": "002594",
    "name": "比亚迪",
    "exchange": "SZ",
    "exchange_name": "深圳证券交易所",
    "canonical_code": "002594.SZ",
}
app._selected_company = lambda: company
app._show_company_banner = lambda selected: None
app.render_financial_trend_page()
"""
    app_test = AppTest.from_string(script).run()
    visible_text = "\n".join(
        str(item.value)
        for group in (
            app_test.title,
            app_test.info,
            app_test.success,
            app_test.warning,
            app_test.caption,
            app_test.markdown,
        )
        for item in group
    )

    assert not app_test.exception
    assert "比亚迪" in visible_text
    assert "标准化接入检查通过" in visible_text
    assert "利润与经营现金方向不一致" in visible_text
    assert len(app_test.metric) == 12
    assert len(app_test.get("link_button")) == 3
    assert app_test.selectbox[0].value == "比亚迪｜002594.SZ"


def test_financial_trend_page_shows_wuliangye_versions_in_streamlit() -> None:
    """Prove Wuliangye's four periods and five vintages render safely."""
    from streamlit.testing.v1 import AppTest

    script = """
from src import app

company = {
    "code": "000858",
    "name": "五粮液",
    "exchange": "SZ",
    "exchange_name": "深圳证券交易所",
    "canonical_code": "000858.SZ",
}
app._selected_company = lambda: company
app._show_company_banner = lambda selected: None
app.render_financial_trend_page()
"""
    app_test = AppTest.from_string(script).run()
    visible_text = "\n".join(
        str(item.value)
        for group in (
            app_test.title,
            app_test.info,
            app_test.success,
            app_test.warning,
            app_test.caption,
            app_test.markdown,
        )
        for item in group
    )

    assert not app_test.exception
    assert "五粮液" in visible_text
    assert "标准化接入检查通过" in visible_text
    assert "追溯调整版本 1 个" in visible_text
    assert len(app_test.metric) == 12
    assert len(app_test.get("link_button")) == 4
    assert app_test.selectbox[0].value == "五粮液｜000858.SZ"


def test_cross_company_comparison_page_shows_common_year_evidence() -> None:
    """Render the comparison page with all five audited companies."""
    from streamlit.testing.v1 import AppTest

    script = """
from src import app

app.render_cross_company_comparison_page()
"""
    app_test = AppTest.from_string(script).run()
    visible_text = "\n".join(
        str(item.value)
        for group in (
            app_test.title,
            app_test.info,
            app_test.success,
            app_test.warning,
            app_test.caption,
            app_test.subheader,
            app_test.markdown,
        )
        for item in group
    )

    assert not app_test.exception
    assert "跨公司横向比较工作台" in visible_text
    assert "跨行业比较（3个研究组）" in visible_text
    assert "行业证据与同行组状态" in visible_text
    assert "已建立同行组候选覆盖：白酒制造" in visible_text
    assert "共同年度检查通过" in visible_text
    assert "不含估值、预测或买卖建议" in visible_text
    assert app_test.multiselect[0].value == [
        "贵州茅台｜600519.SH",
        "五粮液｜000858.SZ",
        "泸州老窖｜000568.SZ",
        "宁德时代｜300750.SZ",
        "比亚迪｜002594.SZ",
    ]
    assert app_test.selectbox[0].value == 2024
    assert len(app_test.metric) == 4
    assert len(app_test.get("link_button")) == 5


def test_cross_company_page_can_select_the_baijiu_peer_candidate() -> None:
    """Switch the page from the default cross-industry view to baijiu."""
    from streamlit.testing.v1 import AppTest

    script = """
from src import app

app.render_cross_company_comparison_page()
"""
    app_test = AppTest.from_string(script).run()
    app_test.multiselect[0].set_value(
        [
            "贵州茅台｜600519.SH",
            "五粮液｜000858.SZ",
            "泸州老窖｜000568.SZ",
        ]
    ).run()
    visible_text = "\n".join(
        str(item.value)
        for group in (
            app_test.subheader,
            app_test.success,
            app_test.warning,
            app_test.caption,
            app_test.markdown,
        )
        for item in group
    )

    assert not app_test.exception
    assert "同行组候选｜白酒制造" in visible_text
    assert "白酒经营质量透视｜2025" in visible_text
    assert "2023—2025经营质量趋势" in visible_text
    assert "不生成综合得分" in visible_text
    assert app_test.selectbox[0].value == 2025
    assert len(app_test.get("link_button")) == 3
