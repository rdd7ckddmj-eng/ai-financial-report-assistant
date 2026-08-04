from copy import deepcopy

import pytest

from src.financial_anomaly_explanation import (
    BYD_FINANCIAL_ANOMALY_EVIDENCE_PATH,
    FINANCIAL_ANOMALY_EVIDENCE_PATH,
    build_financial_anomaly_review,
    load_financial_anomaly_cases,
    load_financial_anomaly_evidence,
)
from src.financial_history import (
    load_verified_financial_history,
    select_financial_history_as_of,
)


def _midea_review():
    points = select_financial_history_as_of(
        load_verified_financial_history("000333"),
        "2026-08-03",
    )["points"]
    components = load_financial_anomaly_evidence()
    return build_financial_anomaly_review(points, components)


def _byd_review():
    points = select_financial_history_as_of(
        load_verified_financial_history("002594"),
        "2026-08-03",
    )["points"]
    components = load_financial_anomaly_evidence(
        BYD_FINANCIAL_ANOMALY_EVIDENCE_PATH
    )
    return build_financial_anomaly_review(points, components)


def test_midea_bridge_reconciles_the_verified_cash_flow_change() -> None:
    components = load_financial_anomaly_evidence()
    review = _midea_review()

    assert len(components) == 14
    assert review["signal_detected"] is True
    assert review["revenue_growth"] == pytest.approx(0.1210909479)
    assert review["attributable_net_profit_growth"] == pytest.approx(
        0.1403363194
    )
    assert review["operating_cash_flow_growth"] == pytest.approx(
        -0.1184177136
    )
    assert review["bridge_current_total"] == 53_345_930_000
    assert review["bridge_comparison_total"] == 60_511_572_000
    assert review["bridge_change_total"] == -7_165_642_000
    assert review["bridge_change_total"] == review[
        "operating_cash_flow_change"
    ]
    assert review["reconciliation_passed"] is True


def test_midea_bridge_ranks_confirmed_drivers_without_inventing_causes() -> None:
    review = _midea_review()

    largest = review["drivers"][0]
    assert largest["component_code"] == "operating_payables"
    assert largest["change_contribution"] == -39_029_016_000
    assert largest["direction"] == "拉低"

    drivers = {
        item["component_code"]: item for item in review["drivers"]
    }
    assert drivers["inventory_change"]["change_contribution"] == (
        17_869_218_000
    )
    assert drivers["operating_receivables"]["change_contribution"] == (
        6_237_564_000
    )
    assert drivers["consolidated_net_profit"]["change_contribution"] == (
        5_762_982_000
    )
    assert "合并净利润" in review["limitation"]
    assert "归母净利润" in review["limitation"]
    assert any("需进一步" in item for item in review["unresolved_questions"])
    assert "不构成投资建议" in review["limitation"]


def test_case_catalog_loads_midea_and_byd_as_separate_evidence_sets() -> None:
    cases = load_financial_anomaly_cases()

    assert len(cases) == 2
    assert [case[0]["company_code"] for case in cases] == [
        "000333",
        "002594",
    ]
    assert [len(case) for case in cases] == [14, 18]


def test_byd_bridge_reconciles_and_ranks_company_specific_questions() -> None:
    review = _byd_review()

    assert review["signal_detected"] is True
    assert review["revenue_growth"] == pytest.approx(0.2901920063)
    assert review["attributable_net_profit_growth"] == pytest.approx(
        0.3399886574
    )
    assert review["operating_cash_flow_growth"] == pytest.approx(
        -0.2137053861
    )
    assert review["bridge_current_total"] == 133_453_873_000
    assert review["bridge_comparison_total"] == 169_725_025_000
    assert review["bridge_change_total"] == -36_271_152_000
    assert review["reconciliation_passed"] is True

    largest = review["drivers"][0]
    assert largest["component_code"] == "operating_payables"
    assert largest["change_contribution"] == -45_177_566_000
    drivers = {
        item["component_code"]: item for item in review["drivers"]
    }
    assert drivers["inventory_change"]["change_contribution"] == (
        -23_646_035_000
    )
    assert drivers["fixed_asset_depreciation"][
        "change_contribution"
    ] == 19_204_658_000
    assert any(
        "存货增加" in item and "扩大" in item
        for item in review["unresolved_questions"]
    )
    assert any(
        "经营性应收" in item and "扩大" in item
        for item in review["unresolved_questions"]
    )


def test_loader_rejects_untrusted_sources(tmp_path) -> None:
    malicious = tmp_path / "malicious.csv"
    malicious.write_text(
        FINANCIAL_ANOMALY_EVIDENCE_PATH.read_text(encoding="utf-8").replace(
            "https://static.cninfo.com.cn/finalpage/2026-03-31/1225065145.PDF",
            "https://example.com/report.pdf",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="官方 HTTPS"):
        load_financial_anomaly_evidence(malicious)


def test_review_rejects_a_tampered_cash_flow_bridge() -> None:
    points = select_financial_history_as_of(
        load_verified_financial_history("000333"),
        "2026-08-03",
    )["points"]
    components = deepcopy(load_financial_anomaly_evidence())
    components[0]["current_value"] += 1_000_000

    with pytest.raises(ValueError, match="不勾稽"):
        build_financial_anomaly_review(points, components)
