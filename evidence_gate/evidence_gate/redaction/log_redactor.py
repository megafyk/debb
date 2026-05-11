from __future__ import annotations

from evidence_gate.contracts import MaskedEvidencePackage
from evidence_gate.redaction.jira_redactor import redact_value


# Correlation fields surfaced from every Quickwit log hit so the agent can
# drive multi-stage queries (identify a failing request → pull its full
# journey) without re-parsing every hit. Order is the fallback priority used
# by prompts/quickwit_query_planning.md.
_CORRELATION_FIELDS = (
    "contextMap.traceId",
    "contextMap.correlationID",
    "contextMap.requestID",
    "requestID",
    "sessionID",
)


def redact_log_hits(
    raw_hits: list[dict], fields_requested: list[str]
) -> list[dict]:
    redacted: list[dict] = []
    for hit in raw_hits:
        row = {field: redact_value(hit[field]) for field in fields_requested if field in hit}
        redacted.append(row)
    return redacted


def extract_correlation_ids(raw_hits: list[dict]) -> dict[str, list[str]]:
    """Collect unique correlation IDs from raw hits, redaction-safety-belted.

    Trace IDs are not PII, but redact_value runs anyway so misconfigured
    fields (e.g. an email accidentally logged as a traceId) don't leak.
    Returns only fields with at least one value, preserving first-seen order.
    """
    out: dict[str, list[str]] = {}
    for field in _CORRELATION_FIELDS:
        values: list[str] = []
        seen: set[str] = set()
        for hit in raw_hits:
            v = hit.get(field)
            if not isinstance(v, str) or not v:
                continue
            redacted = redact_value(v)
            if isinstance(redacted, str) and redacted not in seen:
                seen.add(redacted)
                values.append(redacted)
        if values:
            out[field] = values
    return out


def build_masked_log_package(
    evidence_session_id: str,
    evidence_request_id: str,
    output_profile: str,
    redacted_hits: list[dict],
    hit_count: int,
    audit_ref: str,
    correlation_ids: dict[str, list[str]] | None = None,
    evidence_file: dict | None = None,
) -> MaskedEvidencePackage:
    fields_found = sorted(
        {key for hit in redacted_hits for key in hit}
    )
    masked_data: dict = {
        "hits": redacted_hits,
        "total_hits": hit_count,
        "fields": fields_found,
    }
    if correlation_ids:
        masked_data["correlation_ids"] = correlation_ids
    return MaskedEvidencePackage(
        evidence_session_id=evidence_session_id,
        evidence_request_id=evidence_request_id,
        source_type="quickwit_logs",
        output_profile=output_profile,
        masked_data=masked_data,
        audit_ref=audit_ref,
        evidence_file=evidence_file or {},
    )
