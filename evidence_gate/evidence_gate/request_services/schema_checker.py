from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class CheckResult:
    ok: bool
    errors: list[str]


# Filter field names are concatenated unescaped into the Lucene query string by
# the connector (`f"{field}:..."`). Restrict them to an identifier shape (dots
# for nested fields, `/` for k8s label keys, `-` for hyphenated names) so a
# crafted field like `level:error OR service` can't inject top-level Lucene and
# widen the query beyond the validated filters.
_QW_FIELD_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_./-]*$")


def check_quickwit_plan(plan: dict) -> CheckResult:
    errors = []
    if not plan.get("evidence_session_id"):
        errors.append("missing evidence_session_id")
    if not plan.get("service"):
        errors.append("missing service")
    if not plan.get("datasource_uid"):
        errors.append("missing datasource_uid")

    if not plan.get("from"):
        errors.append("missing from")
    if not plan.get("to"):
        errors.append("missing to")

    if not plan.get("query_intent"):
        errors.append("missing query_intent")
    if not plan.get("filters"):
        errors.append("missing filters")
    if not plan.get("fields_requested"):
        errors.append("missing fields_requested")

    for f in plan.get("filters", []):
        field = f.get("field", "") if isinstance(f, dict) else ""
        if not field or not _QW_FIELD_RE.match(field):
            errors.append(f"invalid filter field name: {field!r}")

    max_hits = plan.get("max_hits", 0)
    if not isinstance(max_hits, int) or max_hits < 1 or max_hits > 1000:
        errors.append("max_hits must be 1-1000")

    return CheckResult(ok=len(errors) == 0, errors=errors)


def check_metabase_plan(plan: dict) -> CheckResult:
    errors = []
    if not plan.get("evidence_session_id"):
        errors.append("missing evidence_session_id")
    if not plan.get("service"):
        errors.append("missing service")
    if not plan.get("entity"):
        errors.append("missing entity")
    if not plan.get("query_intent"):
        errors.append("missing query_intent")
    if not plan.get("facts_requested"):
        errors.append("missing facts_requested")

    return CheckResult(ok=len(errors) == 0, errors=errors)
