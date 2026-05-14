"""All Pydantic contracts for evidence_gate.

Sanitized Jira tickets, evidence sessions, query plans, evidence requests,
masked evidence packages, debug reports, and audit events.
"""
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


# ---- Sanitized ticket -------------------------------------------------------

class SanitizedTicketContext(BaseModel):
    ticket_id: str
    summary: str
    issue_type: str
    priority: str
    status: str
    labels: list[str] = []
    components: list[str] = []
    description_sanitized: str = ""
    comments_sanitized: list[str] = []
    created: datetime | None = None
    updated: datetime | None = None
    issue_links: list[dict] = []
    subtasks: list[str] = []


# ---- Evidence session -------------------------------------------------------

class SensitiveRef(BaseModel):
    value_ref: str
    field_type: str
    semantic_features: dict = {}


class EvidenceSession(BaseModel):
    evidence_session_id: str = Field(default_factory=lambda: f"ESESS-{uuid4().hex[:8]}")
    ticket_id: str
    trace_id: str = ""
    idempotency_key: str = ""
    sensitive_refs: list[SensitiveRef] = []
    source_refs: list[str] = []
    audit_refs: list[str] = []
    # Cached on first fetch so idempotent re-entry returns the same ticket
    # without re-calling Jira and creating duplicate sensitive refs.
    sanitized_ticket: SanitizedTicketContext | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvidenceSessionContext(BaseModel):
    evidence_session_id: str
    ticket_id: str
    trace_id: str
    sanitized_ticket: SanitizedTicketContext
    sensitive_refs: list[SensitiveRef] = []
    source_refs: list[str] = []
    audit_refs: list[str] = []


# ---- Query plans ------------------------------------------------------------

class QueryFilter(BaseModel):
    field: str
    op: str  # =, !=, in, not_in, contains, matches_sensitive_ref
    value: str | list[str] | None = None
    value_ref: str | None = None


class TimeWindow(BaseModel):
    start: str
    end: str


class QuickwitQueryPlan(BaseModel):
    # Mirrors Grafana MetricRequest at the wire boundary: from/to drive the
    # /ds/query body, datasource_uid identifies the Grafana data source that
    # proxies to Quickwit, and ref_id/max_data_points/interval_ms populate the
    # per-query slot. filters/fields_requested/max_hits stay plan-shaped; the
    # connector translates them into the Lucene query string.
    model_config = ConfigDict(populate_by_name=True)

    type: str = "quickwit_query_plan"
    evidence_session_id: str
    service: str
    repository: str = ""
    code_paths: list[str] = []
    datasource_uid: str
    from_: str = Field(alias="from")
    to: str
    ref_id: str = "A"
    max_data_points: int = 100
    interval_ms: int = 1000
    query_intent: str
    filters: list[QueryFilter]
    fields_requested: list[str]
    max_hits: int = Field(default=100, ge=1, le=1000)
    output_profile: str = ""


class QuickwitQueryResult(BaseModel):
    hits: list[dict]
    is_valuable: bool
    reason: str = ""


class MetabaseQueryPlan(BaseModel):
    type: str = "metabase_query_plan"
    evidence_session_id: str
    service: str
    repository: str = ""
    code_paths: list[str] = []
    entity: str
    query_intent: str
    sql_candidate: str = ""
    params: list[dict] = []
    facts_requested: list[str]
    output_profile: str = ""
    database_id: int = 0
    database_type: str = ""
    schema: str = ""


# ---- Evidence request -------------------------------------------------------

class EvidenceRequest(BaseModel):
    evidence_request_id: str = Field(default_factory=lambda: f"EREQ-{uuid4().hex[:8]}")
    evidence_session_id: str
    request_type: str  # quickwit_query_plan, metabase_query_plan
    state: str = "created"  # created, schema_checked, rejected, bounded, connector_running, raw_evidence_stored, redaction_running, masked_package_ready, failed, expired
    plan: dict = {}
    rejection_reason: str = ""
    narrowing_applied: list[str] = []
    evidence_id: str | None = None
    audit_refs: list[str] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---- Masked evidence package ------------------------------------------------

class DiagnosticFeature(BaseModel):
    field: str
    subject_token: str = ""
    features: dict = {}


class MaskedEvidencePackage(BaseModel):
    evidence_id: str = Field(default_factory=lambda: f"EVID-{uuid4().hex[:8]}")
    evidence_session_id: str
    evidence_request_id: str = ""
    source_type: str  # quickwit_logs, metabase_query, jira_ticket
    output_profile: str = ""
    masked_data: dict = {}
    diagnostic_features: list[DiagnosticFeature] = []
    audit_ref: str = ""
    evidence_file: dict = {}  # {"path": "...jsonl", "format": "jsonl", "line_count": N}
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---- Debug report -----------------------------------------------------------

class RejectedHypothesis(BaseModel):
    hypothesis: str
    reason: str


class DebugReport(BaseModel):
    report_id: str = Field(default_factory=lambda: f"RPT-{uuid4().hex[:8]}")
    ticket_id: str
    evidence_session_id: str
    summary: str
    services_inspected: list[str] = []
    code_paths_inspected: list[str] = []
    query_plans_submitted: list[str] = []
    evidence_collected: list[str] = []
    diagnostic_features_used: list[dict] = []
    hypotheses_considered: list[str] = []
    hypotheses_rejected: list[RejectedHypothesis] = []
    most_likely_root_cause: str
    confidence: str  # low, medium, high
    confidence_rationale: str = ""
    suggested_fix: str = ""
    fix_risks: list[str] = []
    verification_steps: list[str] = []
    evidence_ids: list[str] = []
    audit_refs: list[str] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---- Audit ------------------------------------------------------------------

class AuditEvent(BaseModel):
    audit_id: str = Field(default_factory=lambda: f"AUD-{uuid4().hex[:8]}")
    evidence_session_id: str
    event_type: str  # session_created, ticket_fetched, request_created, request_state_changed, evidence_masked, report_submitted
    details: dict = {}
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
