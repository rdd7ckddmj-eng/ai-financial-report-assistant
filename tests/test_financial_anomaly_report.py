from copy import deepcopy

from src.financial_anomaly_explanation import (
    BYD_FINANCIAL_ANOMALY_EVIDENCE_PATH,
    build_financial_anomaly_review,
    load_financial_anomaly_evidence,
)
from src.financial_anomaly_report import (
    build_financial_anomaly_audit_payload,
    build_financial_anomaly_report_html,
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
    return build_financial_anomaly_review(
        points,
        load_financial_anomaly_evidence(),
    )


def _byd_review():
    points = select_financial_history_as_of(
        load_verified_financial_history("002594"),
        "2026-08-03",
    )["points"]
    return build_financial_anomaly_review(
        points,
        load_financial_anomaly_evidence(
            BYD_FINANCIAL_ANOMALY_EVIDENCE_PATH
        ),
    )


def test_report_preserves_source_page_bridge_and_safety_boundary() -> None:
    review = _midea_review()

    html = build_financial_anomaly_report_html(review)
    payload = build_financial_anomaly_audit_payload(review)

    assert "FINANCIAL EXPLANATION AGENT" in html
    assert "美的集团｜财务异常解释" in html
    assert "第 233 页" in html
    assert "经营性应付项目的增加" in html
    assert "https://static.cninfo.com.cn/finalpage/2026-03-31/1225065145.PDF" in html
    assert "待进一步核查" in html
    assert "不构成投资建议" in html
    assert payload["report_type"] == "wfz_financial_anomaly_explanation"
    assert len(payload["evidence_fingerprint"]["value"]) == 64
    assert payload["cash_flow_bridge"]["reconciliation_passed"] is True


def test_report_escapes_text_and_removes_untrusted_links() -> None:
    review = deepcopy(_midea_review())
    review["company_name"] = "<script>alert(1)</script>"
    review["source_url"] = "javascript:alert(1)"

    html = build_financial_anomaly_report_html(review)
    payload = build_financial_anomaly_audit_payload(review)

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "javascript:alert(1)" not in html
    assert payload["evidence"]["source_url"] is None


def test_byd_report_preserves_second_case_source_and_bridge() -> None:
    review = _byd_review()

    html = build_financial_anomaly_report_html(review)
    payload = build_financial_anomaly_audit_payload(review)

    assert "比亚迪｜财务异常解释" in html
    assert "第 239 页" in html
    assert "固定资产折旧" in html
    assert "存货增加对经营现金流的占用为什么扩大" in html
    assert payload["company"]["code"] == "002594"
    assert payload["case"]["period_year"] == 2024
    assert payload["cash_flow_bridge"]["bridge_change_total"] == (
        -36_271_152_000
    )


def test_evidence_fingerprint_changes_when_findings_change() -> None:
    review = _midea_review()
    original = build_financial_anomaly_audit_payload(review)
    changed_review = deepcopy(review)
    changed_review["confirmed_findings"].append("新增核验结论")
    changed = build_financial_anomaly_audit_payload(changed_review)

    assert original["evidence_fingerprint"]["value"] != changed[
        "evidence_fingerprint"
    ]["value"]
