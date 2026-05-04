from __future__ import annotations

from dataclasses import dataclass

from evidence_gate.contracts.evidence_request import EvidenceRequest
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


def validate_quickwit_request(
    plan: dict,
    evidence_session_id: str,
    request_store: EvidenceRequestStore,
) -> PipelineResult:
    request = EvidenceRequest(
        evidence_session_id=evidence_session_id,
        request_type="quickwit_query_plan",
        plan=plan,
    )
    request = request_store.create(request)

    # 1. Schema check
    schema_result = check_quickwit_plan(plan)
    if not schema_result.ok:
        reason = f"schema: {'; '.join(schema_result.errors)}"
        request_store.transition(request.evidence_request_id, "rejected", {"rejection_reason": reason})
        return PipelineResult(request=request, accepted=False, rejection_reason=reason)

    request_store.transition(request.evidence_request_id, "schema_checked")

    # 2. Safety check
    safety_result = check_plan_safety(plan)
    if not safety_result.ok:
        reason = f"safety: {'; '.join(safety_result.violations)}"
        request_store.transition(request.evidence_request_id, "rejected", {"rejection_reason": reason})
        return PipelineResult(request=request, accepted=False, rejection_reason=reason)

    # 3. Bounds check
    bounds_result = check_quickwit_bounds(plan)
    if not bounds_result.ok:
        reason = f"bounds: {bounds_result.rejection_reason}"
        request_store.transition(request.evidence_request_id, "rejected", {"rejection_reason": reason})
        return PipelineResult(request=request, accepted=False, rejection_reason=reason)

    narrowing = bounds_result.narrowing_applied if bounds_result.narrowed else []
    request_store.transition(
        request.evidence_request_id,
        "bounded",
        {"narrowing_applied": narrowing},
    )

    return PipelineResult(request=request, accepted=True, narrowing_applied=narrowing)


def validate_metabase_request(
    plan: dict,
    evidence_session_id: str,
    request_store: EvidenceRequestStore,
) -> PipelineResult:
    request = EvidenceRequest(
        evidence_session_id=evidence_session_id,
        request_type="metabase_query_plan",
        plan=plan,
    )
    request = request_store.create(request)

    # 1. Schema check
    schema_result = check_metabase_plan(plan)
    if not schema_result.ok:
        reason = f"schema: {'; '.join(schema_result.errors)}"
        request_store.transition(request.evidence_request_id, "rejected", {"rejection_reason": reason})
        return PipelineResult(request=request, accepted=False, rejection_reason=reason)

    request_store.transition(request.evidence_request_id, "schema_checked")

    # 2. Safety check
    safety_result = check_plan_safety(plan)
    if not safety_result.ok:
        reason = f"safety: {'; '.join(safety_result.violations)}"
        request_store.transition(request.evidence_request_id, "rejected", {"rejection_reason": reason})
        return PipelineResult(request=request, accepted=False, rejection_reason=reason)

    # 3. Bounds check
    bounds_result = check_metabase_bounds(plan)
    if not bounds_result.ok:
        reason = f"bounds: {bounds_result.rejection_reason}"
        request_store.transition(request.evidence_request_id, "rejected", {"rejection_reason": reason})
        return PipelineResult(request=request, accepted=False, rejection_reason=reason)

    narrowing = bounds_result.narrowing_applied if bounds_result.narrowed else []
    request_store.transition(
        request.evidence_request_id,
        "bounded",
        {"narrowing_applied": narrowing},
    )

    return PipelineResult(request=request, accepted=True, narrowing_applied=narrowing)
