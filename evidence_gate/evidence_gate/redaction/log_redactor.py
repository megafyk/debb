from __future__ import annotations

from evidence_gate.contracts import MaskedEvidencePackage
from evidence_gate.redaction.jira_redactor import redact_text


def _redact_value(value: object) -> object:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: _redact_value(v) for k, v in value.items()}
    return value


def redact_log_hits(
    raw_hits: list[dict], fields_requested: list[str]
) -> list[dict]:
    redacted: list[dict] = []
    for hit in raw_hits:
        row = {}
        for field in fields_requested:
            if field in hit:
                row[field] = _redact_value(hit[field])
        redacted.append(row)
    return redacted


def build_masked_log_package(
    evidence_session_id: str,
    evidence_request_id: str,
    output_profile: str,
    redacted_hits: list[dict],
    hit_count: int,
    audit_ref: str,
) -> MaskedEvidencePackage:
    fields_found = sorted(
        {key for hit in redacted_hits for key in hit}
    )
    return MaskedEvidencePackage(
        evidence_session_id=evidence_session_id,
        evidence_request_id=evidence_request_id,
        source_type="quickwit_logs",
        output_profile=output_profile,
        masked_data={
            "hits": redacted_hits,
            "total_hits": hit_count,
            "fields": fields_found,
        },
        audit_ref=audit_ref,
    )
