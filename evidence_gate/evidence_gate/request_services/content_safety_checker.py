from __future__ import annotations

import re
from dataclasses import dataclass

from evidence_gate.redaction.leakage import (
    CREDENTIAL_PATTERNS,
    PII_PATTERNS,
    collect_text,
)


@dataclass
class SafetyResult:
    ok: bool
    violations: list[str]


_SQL_DANGEROUS = [
    (re.compile(r"(?i)\bSELECT\s+\*"), "SELECT * not allowed"),
    (re.compile(r"(?i)\b(?:DROP|TRUNCATE|DELETE|ALTER|CREATE|INSERT|UPDATE)\s+"), "mutating SQL not allowed"),
    (re.compile(r"(?i)\b(?:UNION\s+SELECT|INTO\s+OUTFILE|LOAD_FILE)\b"), "SQL injection pattern detected"),
]


def check_plan_safety(plan: dict) -> SafetyResult:
    """Scan all string values in a plan dict for unsafe content."""
    violations = []
    text = collect_text(plan)

    for pattern, message in PII_PATTERNS:
        if pattern.search(text):
            violations.append(message)

    for pattern, message in CREDENTIAL_PATTERNS:
        if pattern.search(text):
            violations.append(message)

    sql = plan.get("sql_candidate", "")
    if sql:
        for pattern, message in _SQL_DANGEROUS:
            if pattern.search(sql):
                violations.append(message)

    return SafetyResult(ok=len(violations) == 0, violations=violations)
