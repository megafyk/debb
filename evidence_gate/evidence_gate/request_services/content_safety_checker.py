from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class SafetyResult:
    ok: bool
    violations: list[str]


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

_SQL_DANGEROUS = [
    (re.compile(r"(?i)\bSELECT\s+\*"), "SELECT * not allowed"),
    (re.compile(r"(?i)\b(?:DROP|TRUNCATE|DELETE|ALTER|CREATE|INSERT|UPDATE)\s+"), "mutating SQL not allowed"),
    (re.compile(r"(?i)\b(?:UNION\s+SELECT|INTO\s+OUTFILE|LOAD_FILE)\b"), "SQL injection pattern detected"),
]


def check_plan_safety(plan: dict) -> SafetyResult:
    """Scan all string values in a plan dict for unsafe content."""
    violations = []
    strings = _collect_strings(plan)
    text = " ".join(strings)

    for pattern, message in _PII_PATTERNS:
        if pattern.search(text):
            violations.append(message)

    for pattern, message in _CREDENTIAL_PATTERNS:
        if pattern.search(text):
            violations.append(message)

    # Check sql_candidate specifically
    sql = plan.get("sql_candidate", "")
    if sql:
        for pattern, message in _SQL_DANGEROUS:
            if pattern.search(sql):
                violations.append(message)

    return SafetyResult(ok=len(violations) == 0, violations=violations)


def _collect_strings(obj, depth: int = 0) -> list[str]:
    """Recursively collect all string values from a dict/list."""
    if depth > 10:
        return []
    strings = []
    if isinstance(obj, str):
        strings.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            strings.extend(_collect_strings(v, depth + 1))
    elif isinstance(obj, list):
        for item in obj:
            strings.extend(_collect_strings(item, depth + 1))
    return strings
