from __future__ import annotations

import re
from dataclasses import dataclass, field


_VALID_CONFIDENCE = {"low", "medium", "high"}

# PII patterns — same as content_safety_checker
_PII_PATTERNS = [
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "raw email detected"),
    (re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}\b"), "raw phone number detected"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "raw SSN detected"),
]

_CREDENTIAL_PATTERNS = [
    (re.compile(r"(?i)\b(?:password|passwd|secret|api[_-]?key)\s*[:=]\s*\S+"), "credential assignment detected"),
    (re.compile(r"\b(?:eyJ)[A-Za-z0-9_-]{10,}"), "JWT/token detected"),
    (re.compile(r"(?i)(?:bearer|basic)\s+[A-Za-z0-9+/=_-]{8,}"), "auth header detected"),
]

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

    # 1. Required fields
    for f in ("ticket_id", "evidence_session_id", "summary", "most_likely_root_cause", "confidence"):
        if not report_data.get(f):
            issues.append(f"missing required field: {f}")

    # 2. Confidence validity
    conf = report_data.get("confidence", "")
    if conf and conf not in _VALID_CONFIDENCE:
        issues.append(f"invalid confidence: {conf} (must be low/medium/high)")

    # 3. Evidence citations
    if not report_data.get("evidence_ids"):
        issues.append("no evidence_ids cited")
    if not report_data.get("audit_refs"):
        issues.append("no audit_refs cited")

    # 4. Verification steps
    if not report_data.get("verification_steps"):
        issues.append("no verification_steps provided")

    # 5. PII/credential leakage scan
    text = _collect_text(report_data)
    for pattern, message in _PII_PATTERNS:
        if pattern.search(text):
            issues.append(f"leakage: {message}")
    for pattern, message in _CREDENTIAL_PATTERNS:
        if pattern.search(text):
            issues.append(f"leakage: {message}")

    # 6. Overstatement check
    for pattern in _OVERSTATEMENT_PATTERNS:
        if pattern.search(text):
            issues.append("overstatement: avoid 'proven', 'confirmed', 'definitive' for root cause")

    return ReviewResult(ok=len(issues) == 0, issues=issues)


def _collect_text(obj: object, depth: int = 0) -> str:
    if depth > 10:
        return ""
    if isinstance(obj, str):
        return obj + " "
    if isinstance(obj, dict):
        return " ".join(_collect_text(v, depth + 1) for v in obj.values())
    if isinstance(obj, list):
        return " ".join(_collect_text(item, depth + 1) for item in obj)
    return ""
