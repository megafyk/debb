from __future__ import annotations

from evidence_gate.audit_logger import AuditLogger
from evidence_gate.connectors.metabase_connector import MetabaseConnector
from evidence_gate.connectors.quickwit_connector import QuickwitConnector
from evidence_gate.contracts import MaskedEvidencePackage
from evidence_gate.contracts import MetabaseQueryPlan, QuickwitQueryPlan
from evidence_gate.request_services.bounds_checker import MAX_METABASE_ROWS
from evidence_gate.redaction.db_redactor import (
    build_masked_db_package,
    extract_diagnostic_features,
    redact_db_rows,
)
from evidence_gate.redaction.log_redactor import (
    build_masked_log_package,
    extract_correlation_ids,
    redact_log_hits,
)
from evidence_gate.storage.debug_report_evidence_store import DebugReportEvidenceStore
from evidence_gate.storage.evidence_request_store import EvidenceRequestStore
from evidence_gate.storage.evidence_session_store import EvidenceSessionStore
from evidence_gate.storage.masked_package_store import MaskedPackageStore
from evidence_gate.storage.raw_evidence_store import RawEvidenceStore


def _build_quickwit_translation(plan: QuickwitQueryPlan) -> dict:
    """Build step-2 translation log for a Quickwit plan.

    Preserves ``value_ref`` placeholders — sensitive values are resolved
    inside the connector at execute time and never written here.
    """
    return {
        "translation_type": "quickwit_lucene",
        "datasource_uid": plan.datasource_uid,
        "lucene_filter_shape": [
            f.model_dump(exclude_none=True) for f in plan.filters
        ],
        "fields_requested": plan.fields_requested,
        "max_hits": plan.max_hits,
        "time_window": {"from": plan.from_, "to": plan.to},
    }


def _build_metabase_translation(plan: MetabaseQueryPlan) -> dict:
    """Build step-2 translation log for a Metabase plan.

    Records the agent-supplied ``sql_candidate`` (value_ref placeholders kept
    verbatim) plus which params came from ``value_ref`` vs literal — never the
    resolved values.
    """
    param_names = [p["name"] for p in plan.params if p.get("name")]
    refs = [p["name"] for p in plan.params if p.get("value_ref")]
    literals = [
        p["name"] for p in plan.params
        if p.get("value_ref") is None and "value" in p
    ]
    return {
        "translation_type": "metabase_native_query",
        "sql_candidate": plan.sql_candidate,
        "entity": plan.entity,
        "database_id": plan.database_id,
        "database_type": plan.database_type,
        "schema": plan.schema,
        "param_names": param_names,
        "params_from_refs": refs,
        "params_from_literals": literals,
    }


def _resolve_debug_report_folder(
    session_store: EvidenceSessionStore, evidence_session_id: str,
) -> str:
    """Build the debug_reports/ subdir label: <TICKET_ID>_<DEBUG_SESSION_ID>.

    The DEBUG_SESSION_ID is the W3C / OpenTelemetry trace id minted in
    ``_start_debugging_session`` (the trace_id field doubles as the
    per-debug-session identifier in the folder name). Both halves are
    required — refuse to write evidence under a partial label rather
    than silently produce ``<ticket>_`` or ``_<session>`` directories
    that can't be cleaned up by id later.
    """
    session = session_store.get(evidence_session_id)
    if session is None:
        raise ValueError(f"Session not found: {evidence_session_id}")
    if not session.ticket_id or not session.trace_id:
        raise ValueError(
            f"Session {evidence_session_id} missing ticket_id or trace_id; "
            "cannot build debug_reports folder label",
        )
    return f"{session.ticket_id}_{session.trace_id}"


async def execute_quickwit_request(
    request_id: str,
    request_store: EvidenceRequestStore,
    quickwit_connector: QuickwitConnector,
    raw_store: RawEvidenceStore,
    masked_store: MaskedPackageStore,
    debug_report_evidence_store: DebugReportEvidenceStore,
    session_store: EvidenceSessionStore,
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

        # Step 2: log the redacted translation BEFORE we hit the source. The
        # plan structure is the translation shape; value_ref placeholders are
        # kept verbatim. The folder label is required — evidence is stored under
        # it below — so a missing/incomplete session fails the request here
        # (caught as a connector failure) rather than being skippable.
        folder_id = _resolve_debug_report_folder(session_store, evidence_session_id)
        debug_report_evidence_store.store_translation(
            folder_id, request_id, _build_quickwit_translation(plan),
        )

        result = await quickwit_connector.execute(plan, evidence_session_id)
        raw_hits = result.hits

        raw_store.store(request_id, raw_hits)
        request_store.transition(request_id, "raw_evidence_stored")

        request_store.transition(request_id, "redaction_running")
        redacted = redact_log_hits(raw_hits, plan.fields_requested)
        correlation_ids = extract_correlation_ids(raw_hits)

        # Build the package first so we have an evidence_id, then persist the
        # masked records under debug_reports/<TICKET_ID>_<DEBUG_SESSION_ID>/
        # evidence/<eid>.jsonl. The path + line_count flow back as
        # evidence_file so the agent can cite specific lines as verifiable
        # references in the debug report (which itself lives in the same
        # per-session folder per SKILL.md step 2).
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
            correlation_ids=correlation_ids,
        )
        package.evidence_file = debug_report_evidence_store.store(
            folder_id, package.evidence_id, redacted,
        )
        masked_store.save(package)

        # Step 3: log execution metadata now that we have the evidence_id link.
        debug_report_evidence_store.store_execution(folder_id, request_id, {
            "evidence_request_id": request_id,
            "source_type": "quickwit_grafana_proxy",
            "is_live": quickwit_connector.is_live,
            "hit_count": len(raw_hits),
            "is_valuable": result.is_valuable,
            "reason": result.reason,
            "evidence_id": package.evidence_id,
        })

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
        # Strip the original exception (`from None`) so URLs, auth headers,
        # and other connector-internal details don't leak through MCP error
        # serialization. The audit log retains the state transition.
        raise RuntimeError(f"connector failed for request {request_id}") from None


async def execute_metabase_request(
    request_id: str,
    request_store: EvidenceRequestStore,
    metabase_connector: MetabaseConnector,
    raw_store: RawEvidenceStore,
    masked_store: MaskedPackageStore,
    debug_report_evidence_store: DebugReportEvidenceStore,
    session_store: EvidenceSessionStore,
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

        # Step 2: log the redacted translation before hitting the source. The
        # folder label is required (evidence is stored under it below), so a
        # missing/incomplete session fails the request here.
        folder_id = _resolve_debug_report_folder(session_store, evidence_session_id)
        debug_report_evidence_store.store_translation(
            folder_id, request_id, _build_metabase_translation(plan),
        )

        raw_rows = await metabase_connector.execute(plan, evidence_session_id)

        raw_store.store(request_id, raw_rows)
        request_store.transition(request_id, "raw_evidence_stored")

        # Cap the rows that reach redaction/the agent: Metabase plans carry no
        # row limit, so without this a column-named SELECT (which clears the
        # SELECT*/mutating gates) could enumerate a whole table into the masked
        # package. The full raw set is still kept server-side in raw_store.
        total_rows = len(raw_rows)
        truncated = total_rows > MAX_METABASE_ROWS
        bounded_rows = raw_rows[:MAX_METABASE_ROWS] if truncated else raw_rows

        request_store.transition(request_id, "redaction_running")
        redacted = redact_db_rows(bounded_rows)
        features = extract_diagnostic_features(bounded_rows, plan.entity)

        audit_event = audit_logger.log(
            evidence_session_id,
            "masked_package_built",
            {"request_id": request_id, "row_count": len(bounded_rows)},
        )

        package = build_masked_db_package(
            evidence_session_id=evidence_session_id,
            evidence_request_id=request_id,
            output_profile=plan.output_profile,
            redacted_rows=redacted,
            diagnostic_features=features,
            audit_ref=audit_event.audit_id,
        )
        package.evidence_file = debug_report_evidence_store.store(
            folder_id, package.evidence_id, redacted,
        )
        masked_store.save(package)

        # Step 3: log execution metadata now that we have the evidence_id link.
        debug_report_evidence_store.store_execution(folder_id, request_id, {
            "evidence_request_id": request_id,
            "source_type": "metabase_dataset",
            "is_live": metabase_connector.is_live,
            "row_count": len(bounded_rows),
            "rows_available": total_rows,
            "truncated": truncated,
            "entity": plan.entity,
            "evidence_id": package.evidence_id,
        })

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
        raise RuntimeError(f"connector failed for request {request_id}") from None
