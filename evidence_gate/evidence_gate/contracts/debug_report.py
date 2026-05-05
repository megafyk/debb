from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field


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
