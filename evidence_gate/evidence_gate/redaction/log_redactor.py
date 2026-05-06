from __future__ import annotations

from evidence_gate.contracts import MaskedEvidencePackage
from evidence_gate.redaction.jira_redactor import redact_value


def redact_log_hits(
    raw_hits: list[dict], fields_requested: list[str]
) -> list[dict]:
    redacted: list[dict] = []
    for hit in raw_hits:
        row = {field: redact_value(hit[field]) for field in fields_requested if field in hit}
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
