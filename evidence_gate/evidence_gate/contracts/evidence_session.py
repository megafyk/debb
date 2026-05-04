from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field

from evidence_gate.contracts.sanitized_ticket import SanitizedTicketContext


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
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvidenceSessionContext(BaseModel):
    evidence_session_id: str
    ticket_id: str
    trace_id: str
    sanitized_ticket: SanitizedTicketContext
    sensitive_refs: list[SensitiveRef] = []
    source_refs: list[str] = []
    audit_refs: list[str] = []
