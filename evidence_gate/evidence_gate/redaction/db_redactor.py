from __future__ import annotations

from evidence_gate.contracts.masked_evidence_package import DiagnosticFeature, MaskedEvidencePackage
from evidence_gate.redaction.jira_redactor import redact_text


def _redact_row(row: dict) -> dict:
    result = {}
    for k, v in row.items():
        if isinstance(v, str):
            result[k] = redact_text(v)
        else:
            result[k] = v
    return result


def redact_db_rows(raw_rows: list[dict]) -> list[dict]:
    return [_redact_row(row) for row in raw_rows]


def extract_diagnostic_features(rows: list[dict], entity: str) -> list[DiagnosticFeature]:
    features: list[DiagnosticFeature] = []
    if entity == "account" and rows:
        row = rows[0]
        features.append(DiagnosticFeature(
            field="account_status",
            features={
                "account_exists": True,
                "status": row.get("status", "unknown"),
                "is_locked": bool(row.get("locked")),
                "is_disabled": bool(row.get("disabled")),
            },
        ))
    elif entity == "login_attempt" and rows:
        features.append(DiagnosticFeature(
            field="error_distribution",
            features={
                "entries": [
                    {"error_code": r.get("error_code", ""), "count": r.get("cnt", 0)}
                    for r in rows
                ],
                "total_entries": len(rows),
            },
        ))
    return features


def build_masked_db_package(
    evidence_session_id: str,
    evidence_request_id: str,
    output_profile: str,
    redacted_rows: list[dict],
    diagnostic_features: list[DiagnosticFeature],
    audit_ref: str,
) -> MaskedEvidencePackage:
    return MaskedEvidencePackage(
        evidence_session_id=evidence_session_id,
        evidence_request_id=evidence_request_id,
        source_type="metabase_query",
        output_profile=output_profile,
        masked_data={
            "rows": redacted_rows,
            "row_count": len(redacted_rows),
        },
        diagnostic_features=diagnostic_features,
        audit_ref=audit_ref,
    )
