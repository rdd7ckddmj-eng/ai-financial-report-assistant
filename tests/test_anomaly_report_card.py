from src.anomaly_analogs import AnomalyAnalog
from src.anomaly_report_card import build_anomaly_report_card_html
from src.china_stock import CompanyIdentity, MarketActivityEvent
from src.historical_lens import EventEvidenceChain


def _company() -> CompanyIdentity:
    return {
        "code": "600519",
        "name": "贵州茅台",
        "exchange": "SH",
        "exchange_name": "上海证券交易所",
        "canonical_code": "600519.SH",
    }


def _event() -> MarketActivityEvent:
    return {
        "date": "2026-07-28",
        "event_type": "明显放量 + 普通换手率高位",
        "close": 1423.50,
        "daily_return": 0.031,
        "daily_return_basis": "公开行情源涨跌幅",
        "volume_ratio_20d": 2.5,
        "volume_percentile_250d": 0.99,
        "turnover": 0.041,
        "turnover_percentile_250d": 0.936,
        "turnover_high_candidate": True,
        "limit_up_reference": 0.10,
        "limit_up_candidate": False,
    }


def _chain() -> EventEvidenceChain:
    return {
        "event_date": "2026-07-28",
        "window_days": 7,
        "status": "matched",
        "matches": [
            {
                "source_id": "notice-1",
                "title": "2025年年度权益分派实施公告",
                "published_date": "2026-07-27",
                "source_type": "权益分派",
                "source_url": "https://static.cninfo.com.cn/notice.pdf",
                "evidence_grade": "A",
                "days_before_event": 1,
                "relation": "此前1天公开",
            }
        ],
        "matched_count": 1,
        "same_day_count": 0,
        "nearest_gap_days": 1,
        "future_excluded_count": 3,
        "conclusion": "所选日期此前7天内匹配1条官方公告。",
        "limitation": "时间接近不能证明公告导致行情变化。",
    }


def _analog() -> AnomalyAnalog:
    return {
        "date": "2026-06-18",
        "event_type": "明显放量 + 普通换手率高位",
        "close": 1388.0,
        "daily_return": 0.027,
        "volume_ratio_20d": 2.31,
        "turnover": 0.038,
        "turnover_percentile_250d": 0.91,
        "similarity_score": 0.87,
        "comparable_dimension_count": 4,
        "shared_signals": ["明显放量", "普通换手率高位"],
        "comparison_summary": "共同触发：明显放量、普通换手率高位。",
    }


def test_report_card_preserves_metrics_sources_and_evidence() -> None:
    result = build_anomaly_report_card_html(
        _company(),
        _event(),
        _chain(),
        market_source="腾讯财经公开日线（备用源）",
        turnover_source="新浪财经历史成交额与总股本计算",
        analogs=[_analog()],
        historical_lens_url=(
            "https://fangzhengai.wang/render_historical_lens_page"
        ),
    )

    assert "<!doctype html>" in result
    assert "贵州茅台" in result
    assert "600519.SH" in result
    assert "2026-07-28" in result
    assert "2.50 倍" in result
    assert "93.6%" in result
    assert "2025年年度权益分派实施公告" in result
    assert "https://static.cninfo.com.cn/notice.pdf" in result
    assert "另有 3 条研究日之后公开的公告被排除" in result
    assert "新浪财经历史成交额与总股本计算" in result
    assert "普通换手率不等同于有效换手率" in result
    assert "历史相似异动" in result
    assert "2026-06-18" in result
    assert "规则相似度 87.0%" in result
    assert "共同信号：明显放量、普通换手率高位" in result
    assert result.count("共同信号：明显放量、普通换手率高位") == 1
    assert "可比维度 4 项" in result
    assert (
        "https://fangzhengai.wang/render_historical_lens_page"
        in result
    )
    assert "后来收益没有进入本报告" in result
    assert "不构成买入、卖出或持有建议" in result


def test_report_card_does_not_invent_evidence_when_source_is_unavailable() -> None:
    result = build_anomaly_report_card_html(
        _company(),
        _event(),
        None,
        market_source="测试行情源",
        turnover_source="暂未取得",
    )

    assert "官方公告源暂时不可访问" in result
    assert "没有使用新闻、搜索摘要或" in result
    assert "本次未取得官方公告，因此不对异常原因作任何解释" in result


def test_report_card_escapes_untrusted_text_and_rejects_unsafe_links() -> None:
    company = _company()
    company["name"] = "<script>alert('x')</script>"
    chain = _chain()
    chain["matches"][0]["source_url"] = "javascript:alert(1)"

    result = build_anomaly_report_card_html(
        company,
        _event(),
        chain,
        market_source="<unsafe>",
        turnover_source="测试来源",
        analogs=[_analog()],
        historical_lens_url="javascript:alert(1)",
    )

    assert "<script>alert" not in result
    assert "&lt;script&gt;" in result
    assert "javascript:alert(1)" not in result
    assert "原文链接未通过安全校验" in result
    assert "Historical Lens 链接暂未配置" in result


def test_report_card_explains_when_no_historical_analogs_exist() -> None:
    result = build_anomaly_report_card_html(
        _company(),
        _event(),
        _chain(),
        market_source="测试行情源",
        turnover_source="测试来源",
    )

    assert "当前扫描范围内没有达到最低门槛的更早相似异动" in result
