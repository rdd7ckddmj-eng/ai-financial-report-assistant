"""Attach public-vendor financial analysis without promoting it to verified fact."""

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256

from src.public_financial_history import validate_public_financial_history
from src.research_case import apply_case_patch, validate_research_case


def _validate_current_public_case(case, history, emitted_at):
    validate_research_case(case)
    history = validate_public_financial_history(history)
    if case["scope"]["mode"] != "current":
        raise ValueError("公开源当前版本不能写入历史案件。")
    if case["company"]["canonical_code"] != history["company"]["canonical_code"]:
        raise ValueError("财务资料与案件公司不一致。")
    emitted = datetime.fromisoformat(emitted_at.replace("Z", "+00:00"))
    fetched = datetime.fromisoformat(history["fetched_at"])
    if emitted.tzinfo is None or emitted < fetched:
        raise ValueError("写入时间不能早于取数时间。")
    if case["scope"]["effective_market_date"] < fetched.astimezone(timezone.utc).date().isoformat():
        raise ValueError("当前案件需先推进日期再接收新资料。")
    return history


def build_public_financial_case_patch(case, history, *, emitted_at):
    history = _validate_current_public_case(case, history, emitted_at)
    identity = sha256((case["case_id"] + history["fingerprint"]).encode()).hexdigest()[:24]
    artifact_id = "public-financial-" + identity
    # Analysis artifacts cannot count as reviewed source facts. Keep the
    # existing source evidence and review decisions untouched.
    question = {key: deepcopy(value) for key, value in case["questions"]["financial_quality"].items() if key in {"status", "summary", "next_action", "artifact_ids", "evidence_ids"}}
    question.update(
        artifact_ids=list(dict.fromkeys([*question["artifact_ids"], artifact_id])),
    )
    if question["status"] in {"not_started", "blocked", "in_progress"}:
        question.update(status="in_progress", summary="已取得多年公开财务候选；需官方年报核验。",
                        next_action="进入年报与证据核对关键金额、口径和版本。")
    patch = {
        "patch_id": "public-financial-patch-" + identity,
        "case_id": case["case_id"], "base_revision": case["revision"],
        "canonical_code": case["company"]["canonical_code"],
        "mode": "current", "as_of_date": None, "emitted_at": emitted_at,
        "source_module": "financial_trend",
        "artifact": {
            "artifact_id": artifact_id, "module": "financial_trend",
            "title": f"{history['points'][-1]['period_year']}年公开财务及多年趋势（待核验）",
            "generated_at": emitted_at, "review_status": "not_required",
            "payload": {
                "kind": "analysis_output", "status": "public_unverified",
                "canonical_code": history["company"]["canonical_code"],
                "source_url": history["source_url"], "fetched_at": history["fetched_at"],
                "fingerprint": history["fingerprint"],
                "points": history["points"][-2:], "source_rows": history["source_rows"][-2:],
                "observations": history["observations"], "issues": history["issues"][:6],
                "limitation": history["limitation"],
            },
        },
        "question_updates": {"financial_quality": question},
        "audit_message": "公开财务候选写入为分析产物；没有新增已确认事实，没有改变历史检查点。",
    }
    if not case["case_brief"]["primary_question"]:
        patch["case_brief_update"] = {
            "primary_question": "该公司财务变化在官方年报中能否得到核验？",
            "evidence": {"summary": "已有多年公开源财务候选，尚无新增逐页核验证据。", "artifact_ids": [artifact_id], "evidence_ids": []},
            "next_action": {"module": "financial_snapshot", "action": "核验同年官方年报", "reason": "公开源结果不能替代官方披露与人工复核。"},
        }
    apply_case_patch(case, patch)
    return patch


def build_public_reconciliation_case_patch(case, history, snapshot, *, emitted_at):
    """Persist a reproducible comparison as analysis, never source evidence."""
    from src.public_financial_reconciliation import build_public_financial_reconciliation

    history = _validate_current_public_case(case, history, emitted_at)
    result = build_public_financial_reconciliation(history, snapshot)
    identity = sha256((case['case_id'] + result['fingerprint']).encode()).hexdigest()[:24]
    artifact_id = 'source-comparison-' + identity
    payload = deepcopy(result)
    payload['schema'] = 'public-financial-reconciliation-artifact.v1'
    payload['full_comparison_fingerprint'] = payload.pop('fingerprint')
    payload['kind'] = 'analysis_output'
    # Full comparison remains downloadable. The case stores bounded excerpts.
    for row in payload['rows']:
        row['excerpt'] = row['excerpt'][:160]
    payload['excerpt_storage_limit'] = 160
    counts = {status: sum(row['status'] == status for row in result['rows'])
              for status in ('amount_close', 'amount_difference', 'not_comparable')}
    question = {'artifact_ids': list(dict.fromkeys([
        *case['questions']['financial_quality']['artifact_ids'], artifact_id]))}
    if case['questions']['financial_quality']['status'] in {'not_started', 'blocked', 'in_progress'}:
        question.update(status='in_progress',
            summary=f"{result['report_year']}年两源金额对照：{counts['amount_difference']}项差异、{counts['not_comparable']}项不可比；仍需人工复核。",
            next_action='进入年报快照逐项核对原文；金额相近也不能自动确认。')
    patch = dict(patch_id='source-comparison-patch-' + identity,
        case_id=case['case_id'], base_revision=case['revision'],
        canonical_code=case['company']['canonical_code'], mode='current', as_of_date=None,
        emitted_at=emitted_at, source_module='financial_snapshot',
        artifact=dict(artifact_id=artifact_id, module='financial_snapshot',
            title=f"{result['report_year']}年公开源与年报金额对照（待核验）",
            generated_at=emitted_at, review_status='not_required', payload=payload),
        question_updates={'financial_quality': question},
        audit_message='保存两源金额对照分析；不新增已确认事实，不覆盖人工复核决定，不将差异直接认定为矛盾。')
    if not case['case_brief']['primary_question']:
        patch['case_brief_update'] = dict(
            primary_question='公开财务金额与同年官方年报的数字及口径能否对应？',
            evidence=dict(summary='已有两源对照分析，金额差异原因和相近数字的口径仍待核验。', artifact_ids=[artifact_id], evidence_ids=[]),
            next_action=dict(module='financial_snapshot', action='逐项复核年报金额与口径', reason='两源对照不代替人工判断。'))
    apply_case_patch(case, patch)
    return patch
