from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CheckResult:
    ok: bool
    errors: list[str]


def check_quickwit_plan(plan: dict) -> CheckResult:
    errors = []
    if not plan.get("evidence_session_id"):
        errors.append("missing evidence_session_id")
    if not plan.get("service"):
        errors.append("missing service")
    if not plan.get("index_hint"):
        errors.append("missing index_hint")

    tw = plan.get("time_window")
    if not tw or not tw.get("start") or not tw.get("end"):
        errors.append("missing or incomplete time_window")

    if not plan.get("query_intent"):
        errors.append("missing query_intent")
    if not plan.get("filters"):
        errors.append("missing filters")
    if not plan.get("fields_requested"):
        errors.append("missing fields_requested")

    max_hits = plan.get("max_hits", 0)
    if not isinstance(max_hits, int) or max_hits < 1 or max_hits > 1000:
        errors.append("max_hits must be 1-1000")

    return CheckResult(ok=len(errors) == 0, errors=errors)


def check_metabase_plan(plan: dict) -> CheckResult:
    errors = []
    if not plan.get("evidence_session_id"):
        errors.append("missing evidence_session_id")
    if not plan.get("service"):
        errors.append("missing service")
    if not plan.get("entity"):
        errors.append("missing entity")
    if not plan.get("query_intent"):
        errors.append("missing query_intent")
    if not plan.get("facts_requested"):
        errors.append("missing facts_requested")

    return CheckResult(ok=len(errors) == 0, errors=errors)
