from datetime import date, timedelta

from src.historical_deep_link import parse_historical_deep_link


TODAY = date(2026, 7, 30)


def test_parses_valid_report_deep_link() -> None:
    result = parse_historical_deep_link(
        {
            "code": "600519",
            "date": "2026-06-18",
            "source": "anomaly-report",
        },
        today=TODAY,
    )

    assert result == {
        "code": "600519",
        "event_date": date(2026, 6, 18),
        "source": "anomaly-report",
    }


def test_accepts_list_style_query_params_but_drops_unknown_source() -> None:
    result = parse_historical_deep_link(
        {
            "code": ["000001"],
            "date": ["2024-01-02"],
            "source": ["untrusted"],
        },
        today=TODAY,
    )

    assert result == {
        "code": "000001",
        "event_date": date(2024, 1, 2),
        "source": None,
    }


def test_rejects_invalid_code_or_date() -> None:
    assert (
        parse_historical_deep_link(
            {"code": "600519.SH", "date": "2026-06-18"},
            today=TODAY,
        )
        is None
    )
    assert (
        parse_historical_deep_link(
            {"code": "600519", "date": "18-06-2026"},
            today=TODAY,
        )
        is None
    )


def test_rejects_future_and_out_of_window_dates() -> None:
    for event_date in (
        TODAY + timedelta(days=1),
        TODAY - timedelta(days=365 * 5 + 1),
    ):
        assert (
            parse_historical_deep_link(
                {
                    "code": "600519",
                    "date": event_date.isoformat(),
                },
                today=TODAY,
            )
            is None
        )
