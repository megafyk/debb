from __future__ import annotations

import json

from mcp.server import Server
from mcp.types import TextContent, Tool

from evidence_gate.app.config import settings
from evidence_gate.audit.audit_logger import AuditLogger
from evidence_gate.connectors.jira_connector import JiraConnector
from evidence_gate.connectors.metabase_connector import MetabaseConnector
from evidence_gate.connectors.quickwit_connector import QuickwitConnector
from evidence_gate.contracts.debug_report import DebugReport
from evidence_gate.contracts.evidence_session import (
    EvidenceSession,
    EvidenceSessionContext,
    SensitiveRef,
)
from evidence_gate.request_services.evidence_executor import (
    execute_metabase_request,
    execute_quickwit_request,
)
from evidence_gate.request_services.report_reviewer import review_report
from evidence_gate.request_services.request_pipeline import (
    validate_metabase_request,
    validate_quickwit_request,
)
from evidence_gate.sessions.evidence_session_store import EvidenceSessionStore
from evidence_gate.sessions.sensitive_value_store import SensitiveValueStore
from evidence_gate.storage.evidence_request_store import EvidenceRequestStore
from evidence_gate.storage.json_store import JsonStore
from evidence_gate.storage.jsonl_event_store import JsonlEventStore
from evidence_gate.storage.masked_package_store import MaskedPackageStore
from evidence_gate.storage.raw_evidence_store import RawEvidenceStore


def _build_dependencies():
    data_path = settings.data_path
    session_store = EvidenceSessionStore(data_path)
    sensitive_store = SensitiveValueStore(data_path)
    audit_logger = AuditLogger(JsonlEventStore(data_path / "audit" / "events.jsonl"))
    jira_connector = JiraConnector(settings)
    request_store = EvidenceRequestStore(
        JsonStore(data_path, "evidence_requests"), audit_logger,
    )
    quickwit_connector = QuickwitConnector(settings, sensitive_store, audit_logger)
    metabase_connector = MetabaseConnector(settings, sensitive_store, audit_logger)
    raw_store = RawEvidenceStore(data_path)
    masked_store = MaskedPackageStore(data_path)
    report_store = JsonStore(data_path, "reports")
    return (
        session_store, sensitive_store, audit_logger, jira_connector,
        request_store, quickwit_connector, metabase_connector,
        raw_store, masked_store, report_store,
    )


def register_tools(server: Server) -> None:
    (
        session_store, sensitive_store, audit_logger, jira_connector,
        request_store, quickwit_connector, metabase_connector,
        raw_store, masked_store, report_store,
    ) = _build_dependencies()

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="start_debugging_session",
                description="Start a new debugging session for a Jira ticket. Returns sanitized ticket context and evidence session ID.",
                inputSchema={
                    "type": "object",
                    "required": ["ticket_id_or_url"],
                    "properties": {
                        "ticket_id_or_url": {"type": "string", "description": "Jira ticket ID or URL"},
                        "trace_id": {"type": "string", "description": "Optional trace ID"},
                        "idempotency_key": {"type": "string", "description": "Optional idempotency key"},
                    },
                },
            ),
            Tool(
                name="get_sanitized_jira_ticket",
                description="Get sanitized Jira ticket context for an existing evidence session.",
                inputSchema={
                    "type": "object",
                    "required": ["evidence_session_id"],
                    "properties": {
                        "evidence_session_id": {"type": "string"},
                    },
                },
            ),
            Tool(
                name="create_quickwit_evidence_request",
                description="Submit a Quickwit query plan for validation and execution. Returns evidence request ID and status.",
                inputSchema={
                    "type": "object",
                    "required": ["plan"],
                    "properties": {
                        "plan": {"type": "object", "description": "QuickwitQueryPlan object"},
                    },
                },
            ),
            Tool(
                name="create_metabase_evidence_request",
                description="Submit a Metabase query plan for validation and execution. Returns evidence request ID and status.",
                inputSchema={
                    "type": "object",
                    "required": ["plan"],
                    "properties": {
                        "plan": {"type": "object", "description": "MetabaseQueryPlan object"},
                    },
                },
            ),
            Tool(
                name="get_evidence_request_status",
                description="Check the status of an evidence request.",
                inputSchema={
                    "type": "object",
                    "required": ["evidence_request_id"],
                    "properties": {
                        "evidence_request_id": {"type": "string"},
                    },
                },
            ),
            Tool(
                name="get_masked_evidence_package",
                description="Get the masked evidence package for a completed evidence request. Only available after request reaches masked_package_ready state.",
                inputSchema={
                    "type": "object",
                    "required": ["evidence_id"],
                    "properties": {
                        "evidence_id": {"type": "string", "description": "Evidence ID from the completed request"},
                    },
                },
            ),
            Tool(
                name="submit_debug_report",
                description="Submit a debug report for review. The report is validated for safety (no PII/credentials), completeness (evidence citations, verification steps), and quality (confidence calibration, no overstatement). Returns review result and report ID if accepted.",
                inputSchema={
                    "type": "object",
                    "required": ["report"],
                    "properties": {
                        "report": {"type": "object", "description": "DebugReport object matching the debug_report schema"},
                    },
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        if name == "start_debugging_session":
            return await _start_debugging_session(
                arguments["ticket_id_or_url"],
                arguments.get("trace_id", ""),
                arguments.get("idempotency_key", ""),
                session_store,
                sensitive_store,
                audit_logger,
                jira_connector,
            )
        elif name == "get_sanitized_jira_ticket":
            return await _get_sanitized_jira_ticket(
                arguments["evidence_session_id"],
                session_store,
                jira_connector,
            )
        elif name == "create_quickwit_evidence_request":
            return await _create_quickwit_evidence_request(
                arguments["plan"], request_store, quickwit_connector,
                raw_store, masked_store, audit_logger,
            )
        elif name == "create_metabase_evidence_request":
            return await _create_metabase_evidence_request(
                arguments["plan"], request_store, metabase_connector,
                raw_store, masked_store, audit_logger,
            )
        elif name == "get_evidence_request_status":
            return await _get_evidence_request_status(
                arguments["evidence_request_id"], request_store,
            )
        elif name == "get_masked_evidence_package":
            return await _get_masked_evidence_package(
                arguments["evidence_id"], masked_store,
            )
        elif name == "submit_debug_report":
            return await _submit_debug_report(
                arguments["report"], report_store, audit_logger,
            )
        else:
            return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]


def _parse_ticket_id(ticket_id_or_url: str) -> str:
    # Handle URLs like https://domain.atlassian.net/browse/BUG-123
    if "/" in ticket_id_or_url:
        return ticket_id_or_url.rstrip("/").split("/")[-1]
    return ticket_id_or_url


async def _start_debugging_session(
    ticket_id_or_url: str,
    trace_id: str,
    idempotency_key: str,
    session_store: EvidenceSessionStore,
    sensitive_store: SensitiveValueStore,
    audit_logger: AuditLogger,
    jira_connector: JiraConnector,
) -> list[TextContent]:
    ticket_id = _parse_ticket_id(ticket_id_or_url)

    # Check for existing session with same idempotency key or ticket
    if idempotency_key:
        existing = session_store.find_by_ticket(ticket_id)
        if existing and existing.idempotency_key == idempotency_key:
            sanitized, _ = jira_connector.fetch_and_sanitize(
                ticket_id, existing.evidence_session_id, sensitive_store,
            )
            ctx = EvidenceSessionContext(
                evidence_session_id=existing.evidence_session_id,
                ticket_id=ticket_id,
                trace_id=existing.trace_id,
                sanitized_ticket=sanitized,
                sensitive_refs=existing.sensitive_refs,
                source_refs=existing.source_refs,
                audit_refs=existing.audit_refs,
            )
            return [TextContent(type="text", text=ctx.model_dump_json(indent=2))]

    # Create new session
    session = EvidenceSession(
        ticket_id=ticket_id,
        trace_id=trace_id,
        idempotency_key=idempotency_key,
    )

    # Fetch and sanitize Jira
    sanitized, sensitive_refs = jira_connector.fetch_and_sanitize(
        ticket_id, session.evidence_session_id, sensitive_store,
    )

    # Store sensitive refs on session
    session.sensitive_refs = sensitive_refs

    # Log audit event
    audit_event = audit_logger.log(
        session.evidence_session_id,
        "session_created",
        {"ticket_id": ticket_id, "trace_id": trace_id},
    )
    session.audit_refs.append(audit_event.audit_id)

    source = "jira_rest" if jira_connector.is_live else "fixture"
    ticket_audit = audit_logger.log(
        session.evidence_session_id,
        "ticket_fetched",
        {"ticket_id": ticket_id, "source": source},
    )
    session.audit_refs.append(ticket_audit.audit_id)

    # Save session
    session_store.save(session)

    # Build response
    ctx = EvidenceSessionContext(
        evidence_session_id=session.evidence_session_id,
        ticket_id=ticket_id,
        trace_id=trace_id,
        sanitized_ticket=sanitized,
        sensitive_refs=session.sensitive_refs,
        source_refs=session.source_refs,
        audit_refs=session.audit_refs,
    )
    return [TextContent(type="text", text=ctx.model_dump_json(indent=2))]


async def _get_sanitized_jira_ticket(
    evidence_session_id: str,
    session_store: EvidenceSessionStore,
    jira_connector: JiraConnector,
) -> list[TextContent]:
    session = session_store.get(evidence_session_id)
    if not session:
        return [TextContent(type="text", text=f'{{"error": "Session not found: {evidence_session_id}"}}')]

    sanitized, _ = jira_connector.fetch_and_sanitize(session.ticket_id)
    return [TextContent(type="text", text=sanitized.model_dump_json(indent=2))]


async def _create_metabase_evidence_request(
    plan: dict,
    request_store: EvidenceRequestStore,
    metabase_connector: MetabaseConnector,
    raw_store: RawEvidenceStore,
    masked_store: MaskedPackageStore,
    audit_logger: AuditLogger,
) -> list[TextContent]:
    session_id = plan.get("evidence_session_id", "")
    if not session_id:
        return [TextContent(type="text", text=json.dumps({"error": "missing evidence_session_id in plan"}))]

    # Validate the plan
    result = validate_metabase_request(plan, session_id, request_store)

    if not result.accepted:
        response = {
            "evidence_request_id": result.request.evidence_request_id,
            "state": result.request.state,
            "accepted": False,
            "rejection_reason": result.rejection_reason,
        }
        return [TextContent(type="text", text=json.dumps(response, indent=2))]

    # Execute: validated plan → connector → raw store → redact → masked package
    package = await execute_metabase_request(
        request_id=result.request.evidence_request_id,
        request_store=request_store,
        metabase_connector=metabase_connector,
        raw_store=raw_store,
        masked_store=masked_store,
        audit_logger=audit_logger,
        evidence_session_id=session_id,
    )

    response = {
        "evidence_request_id": result.request.evidence_request_id,
        "state": "masked_package_ready",
        "accepted": True,
        "evidence_id": package.evidence_id,
    }
    if result.narrowing_applied:
        response["narrowing_applied"] = result.narrowing_applied

    return [TextContent(type="text", text=json.dumps(response, indent=2))]


async def _create_quickwit_evidence_request(
    plan: dict,
    request_store: EvidenceRequestStore,
    quickwit_connector: QuickwitConnector,
    raw_store: RawEvidenceStore,
    masked_store: MaskedPackageStore,
    audit_logger: AuditLogger,
) -> list[TextContent]:
    session_id = plan.get("evidence_session_id", "")
    if not session_id:
        return [TextContent(type="text", text=json.dumps({"error": "missing evidence_session_id in plan"}))]

    # Validate the plan
    result = validate_quickwit_request(plan, session_id, request_store)

    if not result.accepted:
        response = {
            "evidence_request_id": result.request.evidence_request_id,
            "state": result.request.state,
            "accepted": False,
            "rejection_reason": result.rejection_reason,
        }
        return [TextContent(type="text", text=json.dumps(response, indent=2))]

    # Execute: validated plan → connector → raw store → redact → masked package
    package = await execute_quickwit_request(
        request_id=result.request.evidence_request_id,
        request_store=request_store,
        quickwit_connector=quickwit_connector,
        raw_store=raw_store,
        masked_store=masked_store,
        audit_logger=audit_logger,
        evidence_session_id=session_id,
    )

    response = {
        "evidence_request_id": result.request.evidence_request_id,
        "state": "masked_package_ready",
        "accepted": True,
        "evidence_id": package.evidence_id,
    }
    if result.narrowing_applied:
        response["narrowing_applied"] = result.narrowing_applied

    return [TextContent(type="text", text=json.dumps(response, indent=2))]


async def _get_masked_evidence_package(
    evidence_id: str,
    masked_store: MaskedPackageStore,
) -> list[TextContent]:
    package = masked_store.load(evidence_id)
    if not package:
        return [TextContent(type="text", text=json.dumps({"error": f"Package not found: {evidence_id}"}))]
    return [TextContent(type="text", text=package.model_dump_json(indent=2))]


async def _get_evidence_request_status(
    evidence_request_id: str,
    request_store: EvidenceRequestStore,
) -> list[TextContent]:
    request = request_store.get(evidence_request_id)
    if not request:
        return [TextContent(type="text", text=json.dumps({"error": f"Request not found: {evidence_request_id}"}))]

    response = {
        "evidence_request_id": request.evidence_request_id,
        "evidence_session_id": request.evidence_session_id,
        "state": request.state,
        "request_type": request.request_type,
        "rejection_reason": request.rejection_reason or None,
        "narrowing_applied": request.narrowing_applied or None,
        "evidence_id": request.evidence_id,
        "audit_refs": request.audit_refs,
    }
    return [TextContent(type="text", text=json.dumps(response, indent=2))]


async def _submit_debug_report(
    report_data: dict,
    report_store: JsonStore,
    audit_logger: AuditLogger,
) -> list[TextContent]:
    # Review the report
    result = review_report(report_data)

    if not result.ok:
        return [TextContent(type="text", text=json.dumps({
            "accepted": False,
            "issues": result.issues,
        }, indent=2))]

    # Parse into model (validates structure)
    try:
        report = DebugReport.model_validate(report_data)
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({
            "accepted": False,
            "issues": [f"validation error: {e}"],
        }, indent=2))]

    # Store the report
    report_store.save(report.report_id, report)

    # Audit
    audit_logger.log(
        report.evidence_session_id,
        "report_submitted",
        {"report_id": report.report_id, "confidence": report.confidence},
    )

    return [TextContent(type="text", text=json.dumps({
        "accepted": True,
        "report_id": report.report_id,
        "review_issues": [],
    }, indent=2))]
