from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field


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
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
