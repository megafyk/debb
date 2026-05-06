from __future__ import annotations

from dataclasses import dataclass

from evidence_gate.contracts import EvidenceRequest
from evidence_gate.request_services.bounds_checker import (
    check_metabase_bounds,
    check_quickwit_bounds,
)
from evidence_gate.request_services.content_safety_checker import check_plan_safety
from evidence_gate.request_services.schema_checker import (
    check_metabase_plan,
    check_quickwit_plan,
)
from evidence_gate.storage.evidence_request_store import EvidenceRequestStore


@dataclass
class PipelineResult:
    request: EvidenceRequest
    accepted: bool
    rejection_reason: str = ""
    narrowing_applied: list[str] | None = None


def _run_pipeline(
    plan: dict,
    evidence_session_id: str,
    request_type: str,
    schema_check,
    bounds_check,
    request_store: EvidenceRequestStore,
) -> PipelineResult:
    request = request_store.create(EvidenceRequest(
        evidence_session_id=evidence_session_id,
        request_type=request_type,
        plan=plan,
    ))

    schema_result = schema_check(plan)
    if not schema_result.ok:
        reason = f"schema: {'; '.join(schema_result.errors)}"
        request = request_store.transition(
            request.evidence_request_id, "rejected", {"rejection_reason": reason},
        )
        return PipelineResult(request=request, accepted=False, rejection_reason=reason)

    request = request_store.transition(request.evidence_request_id, "schema_checked")

    safety_result = check_plan_safety(plan)
    if not safety_result.ok:
        reason = f"safety: {'; '.join(safety_result.violations)}"
        request = request_store.transition(
            request.evidence_request_id, "rejected", {"rejection_reason": reason},
        )
        return PipelineResult(request=request, accepted=False, rejection_reason=reason)

    bounds_result = bounds_check(plan)
    if not bounds_result.ok:
        reason = f"bounds: {bounds_result.rejection_reason}"
        request = request_store.transition(
            request.evidence_request_id, "rejected", {"rejection_reason": reason},
        )
        return PipelineResult(request=request, accepted=False, rejection_reason=reason)

    narrowing = bounds_result.narrowing_applied
    transition_details: dict = {"narrowing_applied": narrowing}
    if bounds_result.adjusted_plan is not None:
        transition_details["plan"] = bounds_result.adjusted_plan
    request = request_store.transition(
        request.evidence_request_id, "bounded", transition_details,
    )

    return PipelineResult(request=request, accepted=True, narrowing_applied=narrowing)


def validate_quickwit_request(
    plan: dict,
    evidence_session_id: str,
    request_store: EvidenceRequestStore,
) -> PipelineResult:
    return _run_pipeline(
        plan, evidence_session_id, "quickwit_query_plan",
        check_quickwit_plan, check_quickwit_bounds, request_store,
    )


def validate_metabase_request(
    plan: dict,
    evidence_session_id: str,
    request_store: EvidenceRequestStore,
) -> PipelineResult:
    return _run_pipeline(
        plan, evidence_session_id, "metabase_query_plan",
        check_metabase_plan, check_metabase_bounds, request_store,
    )
