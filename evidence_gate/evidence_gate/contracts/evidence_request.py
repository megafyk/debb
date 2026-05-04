from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field


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
