from __future__ import annotations

import re
from dataclasses import dataclass, field

from evidence_gate.redaction.leakage import (
    CREDENTIAL_PATTERNS,
    PII_PATTERNS,
    collect_text,
)


_VALID_CONFIDENCE = {"low", "medium", "high"}

_OVERSTATEMENT_PATTERNS = [
    re.compile(r"(?i)\b(?:proven|confirmed|definitive|certain)\b.*root\s*cause"),
    re.compile(r"(?i)\bthe\s+AI\s+proved\b"),
]


@dataclass
class ReviewResult:
    ok: bool
    issues: list[str] = field(default_factory=list)


def review_report(report_data: dict) -> ReviewResult:
    """Programmatic review of a debug report for safety and quality."""
    issues: list[str] = []

    for f in ("ticket_id", "evidence_session_id", "summary", "most_likely_root_cause", "confidence"):
        if not report_data.get(f):
            issues.append(f"missing required field: {f}")

    conf = report_data.get("confidence", "")
    if conf and conf not in _VALID_CONFIDENCE:
        issues.append(f"invalid confidence: {conf} (must be low/medium/high)")

    if not report_data.get("evidence_ids"):
        issues.append("no evidence_ids cited")
    if not report_data.get("audit_refs"):
        issues.append("no audit_refs cited")

    if not report_data.get("verification_steps"):
        issues.append("no verification_steps provided")

    text = collect_text(report_data)
    for pattern, message in PII_PATTERNS:
        if pattern.search(text):
            issues.append(f"leakage: {message}")
    for pattern, message in CREDENTIAL_PATTERNS:
        if pattern.search(text):
            issues.append(f"leakage: {message}")

    for pattern in _OVERSTATEMENT_PATTERNS:
        if pattern.search(text):
            issues.append("overstatement: avoid 'proven', 'confirmed', 'definitive' for root cause")

    return ReviewResult(ok=len(issues) == 0, issues=issues)
