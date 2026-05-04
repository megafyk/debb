from __future__ import annotations

from evidence_gate.redaction.log_redactor import redact_log_hits, build_masked_log_package


def test_redact_email_in_logs():
    raw = [{"message": "error for user@test.com"}]
    redacted = redact_log_hits(raw, ["message"])
    assert "[REDACTED_EMAIL]" in redacted[0]["message"]
    assert "user@test.com" not in redacted[0]["message"]


def test_redact_phone_in_logs():
    raw = [{"details": "called +1-555-123-4567 and failed"}]
    redacted = redact_log_hits(raw, ["details"])
    assert "555-123-4567" not in redacted[0]["details"]


def test_field_projection():
    raw = [{"a": "1", "b": "2", "c": "3", "d": "4", "e": "5"}]
    redacted = redact_log_hits(raw, ["a", "c"])
    assert set(redacted[0].keys()) == {"a", "c"}


def test_nested_dict_redacted():
    raw = [{"details": {"email": "a@b.com", "ok": "fine"}}]
    redacted = redact_log_hits(raw, ["details"])
    nested = redacted[0]["details"]
    assert "a@b.com" not in str(nested)
    assert "[REDACTED_EMAIL]" in str(nested)


def test_build_masked_package():
    hits = [
        {"timestamp": "2026-01-01T00:01:00Z", "error_code": "FAIL"},
        {"timestamp": "2026-01-01T00:02:00Z", "error_code": "TIMEOUT"},
    ]
    pkg = build_masked_log_package(
        evidence_session_id="ESESS-1",
        evidence_request_id="EREQ-abc",
        output_profile="default",
        redacted_hits=hits,
        hit_count=2,
        audit_ref="AUD-xyz",
    )
    assert pkg.source_type == "quickwit_logs"
    assert pkg.masked_data["total_hits"] == 2
    assert len(pkg.masked_data["hits"]) == 2
    assert sorted(pkg.masked_data["fields"]) == ["error_code", "timestamp"]
    assert pkg.audit_ref == "AUD-xyz"
