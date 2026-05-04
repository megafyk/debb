from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    audit_id: str = Field(default_factory=lambda: f"AUD-{uuid4().hex[:8]}")
    evidence_session_id: str
    event_type: str  # session_created, ticket_fetched, request_created, request_state_changed, evidence_masked, report_submitted
    details: dict = {}
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
