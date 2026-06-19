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

# `schema` is substituted into the SQL verbatim by the Metabase connector
# (`sql.replace("{schema}", plan.schema)`), so it must be a bare SQL identifier.
# Allowing anything else lets an agent route DROP/UNION SELECT through `schema`
# and slip past the sql_candidate denylist below.
_SQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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
    schema = plan.get("schema", "") or ""
    if schema and not _SQL_IDENTIFIER_RE.match(schema):
        violations.append("schema must be a bare SQL identifier")
    if sql:
        # Scan the SQL as it will actually execute: the connector substitutes
        # `{schema}` before running it, so the denylist must see the same
        # string, not just the pre-substitution sql_candidate.
        effective_sql = sql.replace("{schema}", schema) if schema else sql
        for pattern, message in _SQL_DANGEROUS:
            if pattern.search(effective_sql):
                violations.append(message)

    return SafetyResult(ok=len(violations) == 0, violations=violations)
