from __future__ import annotations

from evidence_gate.audit_logger import AuditLogger
from evidence_gate.connectors.metabase_connector import MetabaseConnector
from evidence_gate.connectors.quickwit_connector import QuickwitConnector
from evidence_gate.contracts import MaskedEvidencePackage
from evidence_gate.contracts import MetabaseQueryPlan, QuickwitQueryPlan
from evidence_gate.redaction.db_redactor import (
    build_masked_db_package,
    extract_diagnostic_features,
    redact_db_rows,
)
from evidence_gate.redaction.log_redactor import build_masked_log_package, redact_log_hits
from evidence_gate.storage.evidence_request_store import EvidenceRequestStore
from evidence_gate.storage.masked_package_store import MaskedPackageStore
from evidence_gate.storage.raw_evidence_store import RawEvidenceStore


async def execute_quickwit_request(
    request_id: str,
    request_store: EvidenceRequestStore,
    quickwit_connector: QuickwitConnector,
    raw_store: RawEvidenceStore,
    masked_store: MaskedPackageStore,
    audit_logger: AuditLogger,
    evidence_session_id: str,
) -> MaskedEvidencePackage:
    request = request_store.get(request_id)
    if request is None:
        raise ValueError(f"Request not found: {request_id}")
    if request.state != "bounded":
        raise ValueError(f"Request not in bounded state: {request.state}")

    try:
        request_store.transition(request_id, "connector_running")

        plan = QuickwitQueryPlan.model_validate(request.plan)
        raw_hits = await quickwit_connector.execute(plan, evidence_session_id)

        raw_store.store(request_id, raw_hits)
        request_store.transition(request_id, "raw_evidence_stored")

        request_store.transition(request_id, "redaction_running")
        redacted = redact_log_hits(raw_hits, plan.fields_requested)

        audit_event = audit_logger.log(
            evidence_session_id,
            "masked_package_built",
            {"request_id": request_id, "hit_count": len(raw_hits)},
        )

        package = build_masked_log_package(
            evidence_session_id=evidence_session_id,
            evidence_request_id=request_id,
            output_profile=plan.output_profile,
            redacted_hits=redacted,
            hit_count=len(raw_hits),
            audit_ref=audit_event.audit_id,
        )
        masked_store.save(package)

        request_store.transition(
            request_id,
            "masked_package_ready",
            {"evidence_id": package.evidence_id},
        )
        return package

    except Exception:
        try:
            request_store.transition(request_id, "failed")
        except ValueError:
            pass
        raise


async def execute_metabase_request(
    request_id: str,
    request_store: EvidenceRequestStore,
    metabase_connector: MetabaseConnector,
    raw_store: RawEvidenceStore,
    masked_store: MaskedPackageStore,
    audit_logger: AuditLogger,
    evidence_session_id: str,
) -> MaskedEvidencePackage:
    request = request_store.get(request_id)
    if request is None:
        raise ValueError(f"Request not found: {request_id}")
    if request.state != "bounded":
        raise ValueError(f"Request not in bounded state: {request.state}")

    try:
        request_store.transition(request_id, "connector_running")
        plan = MetabaseQueryPlan.model_validate(request.plan)
        raw_rows = await metabase_connector.execute(plan, evidence_session_id)

        raw_store.store(request_id, raw_rows)
        request_store.transition(request_id, "raw_evidence_stored")

        request_store.transition(request_id, "redaction_running")
        redacted = redact_db_rows(raw_rows)
        features = extract_diagnostic_features(raw_rows, plan.entity)

        audit_event = audit_logger.log(
            evidence_session_id,
            "masked_package_built",
            {"request_id": request_id, "row_count": len(raw_rows)},
        )

        package = build_masked_db_package(
            evidence_session_id=evidence_session_id,
            evidence_request_id=request_id,
            output_profile=plan.output_profile,
            redacted_rows=redacted,
            diagnostic_features=features,
            audit_ref=audit_event.audit_id,
        )
        masked_store.save(package)

        request_store.transition(
            request_id,
            "masked_package_ready",
            {"evidence_id": package.evidence_id},
        )
        return package

    except Exception:
        try:
            request_store.transition(request_id, "failed")
        except ValueError:
            pass
        raise
