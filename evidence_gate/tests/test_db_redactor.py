from __future__ import annotations

from evidence_gate.contracts import DiagnosticFeature
from evidence_gate.redaction.db_redactor import (
    build_masked_db_package,
    extract_diagnostic_features,
    redact_db_rows,
)


def test_redact_db_rows_strips_email():
    rows = [{"status": "active", "email": "user@example.com"}]
    redacted = redact_db_rows(rows)
    assert "[REDACTED_EMAIL]" in redacted[0]["email"]
    assert redacted[0]["status"] == "active"


def test_redact_db_rows_preserves_numbers():
    rows = [{"cnt": 42, "locked": False}]
    redacted = redact_db_rows(rows)
    assert redacted[0]["cnt"] == 42
    assert redacted[0]["locked"] is False


def test_redact_db_rows_recurses_into_dict_column():
    rows = [{"id": 1, "metadata": {"contact_email": "secret@evil.com", "note": "ok"}}]
    redacted = redact_db_rows(rows)
    flat = str(redacted[0]["metadata"])
    assert "secret@evil.com" not in flat
    assert "[REDACTED_EMAIL]" in flat
    assert redacted[0]["metadata"]["note"] == "ok"


def test_redact_db_rows_recurses_into_list_column():
    rows = [{"id": 1, "tags": ["needs-review", "email: trail@bad.io"]}]
    redacted = redact_db_rows(rows)
    flat = str(redacted[0]["tags"])
    assert "trail@bad.io" not in flat
    assert "[REDACTED_EMAIL]" in flat


def test_redact_db_rows_deeply_nested():
    rows = [{"audit": [{"who": "leak@x.com", "where": {"phone": "+1-555-123-4567"}}]}]
    redacted = redact_db_rows(rows)
    flat = str(redacted[0]["audit"])
    assert "leak@x.com" not in flat
    assert "555-123-4567" not in flat


def test_extract_features_account():
    rows = [{"status": "active", "locked": False, "disabled": False}]
    features = extract_diagnostic_features(rows, "account")
    assert len(features) == 1
    assert features[0].field == "account_status"
    assert features[0].features["account_exists"] is True
    assert features[0].features["is_locked"] is False


def test_extract_features_login_attempt():
    rows = [
        {"error_code": "PHONE_NORMALIZATION_FAILED", "cnt": 42},
        {"error_code": "ACCOUNT_LOOKUP_FAILED", "cnt": 15},
    ]
    features = extract_diagnostic_features(rows, "login_attempt")
    assert len(features) == 1
    assert features[0].field == "error_distribution"
    assert features[0].features["total_entries"] == 2


def test_extract_features_empty_rows():
    features = extract_diagnostic_features([], "account")
    assert features == []


def test_build_masked_db_package():
    pkg = build_masked_db_package(
        evidence_session_id="ESESS-1",
        evidence_request_id="REQ-1",
        output_profile="summary",
        redacted_rows=[{"status": "active"}],
        diagnostic_features=[DiagnosticFeature(field="test", features={"ok": True})],
        audit_ref="AUD-1",
    )
    assert pkg.source_type == "metabase_query"
    assert pkg.masked_data["row_count"] == 1
    assert pkg.evidence_id.startswith("EVID-")
    assert pkg.audit_ref == "AUD-1"
