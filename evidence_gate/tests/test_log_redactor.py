from __future__ import annotations

from evidence_gate.redaction.log_redactor import (
    build_masked_log_package,
    extract_correlation_ids,
    redact_log_hits,
)


def test_redact_email_in_logs():
    raw = [{"message": "error for user@test.com"}]
    redacted = redact_log_hits(raw, ["message"])
    assert "[REDACTED_EMAIL]" in redacted[0]["message"]
    assert "user@test.com" not in redacted[0]["message"]


def test_redact_phone_in_logs():
    raw = [{"details": "called +1-555-123-4567 and failed"}]
    redacted = redact_log_hits(raw, ["details"])
    assert "555-123-4567" not in redacted[0]["details"]


def test_redact_vn_intl_phone_in_logs():
    # JSON-embedded Vietnamese international format (no leading `+`) leaked
    # through TTSTK-3919 / XLSCVD-218 masked evidence. The 11-12 digit
    # 84-prefixed shape should be redacted alongside the other phone formats.
    raw = [{"message": '{"msisdn":"84974515324","receiver":"84983851285"}'}]
    redacted = redact_log_hits(raw, ["message"])
    assert "84974515324" not in redacted[0]["message"]
    assert "84983851285" not in redacted[0]["message"]
    assert "[REDACTED_PHONE]" in redacted[0]["message"]


def test_redact_vn_intl_phone_in_structured_field():
    raw = [{"contextMap.msisdn": "84974515324"}]
    redacted = redact_log_hits(raw, ["contextMap.msisdn"])
    assert redacted[0]["contextMap.msisdn"] == "[REDACTED_PHONE]"


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


def test_list_field_redacted():
    raw = [{
        "headers": [
            "Authorization: Bearer eyJabcdefghij1234567890.foo.bar",
            "X-Email: leak@example.com",
        ],
    }]
    redacted = redact_log_hits(raw, ["headers"])
    flat = str(redacted[0]["headers"])
    assert "leak@example.com" not in flat
    assert "eyJabcdefghij" not in flat
    assert "[REDACTED_EMAIL]" in flat
    assert "[REDACTED_TOKEN]" in flat


def test_dict_inside_list_redacted():
    raw = [{"events": [{"actor": "user@x.com"}, {"actor": "ok"}]}]
    redacted = redact_log_hits(raw, ["events"])
    assert "user@x.com" not in str(redacted[0]["events"])
    assert redacted[0]["events"][0]["actor"] == "[REDACTED_EMAIL]"
    assert redacted[0]["events"][1]["actor"] == "ok"


def test_deeply_nested_structure():
    raw = [{"a": {"b": [{"c": ["touch@me.com"]}]}}]
    redacted = redact_log_hits(raw, ["a"])
    assert "touch@me.com" not in str(redacted)
    assert "[REDACTED_EMAIL]" in str(redacted)


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
    assert "correlation_ids" not in pkg.masked_data  # absent when none present


def test_extract_correlation_ids_priority_and_dedup():
    raw = [
        {"contextMap.traceId": "T1", "contextMap.correlationID": "C1", "level": "INFO"},
        {"contextMap.traceId": "T1", "requestID": "R1", "level": "ERROR"},
        {"contextMap.traceId": "T2", "sessionID": "S1"},
        {"contextMap.traceId": "", "requestID": None},  # ignored
    ]
    ids = extract_correlation_ids(raw)
    assert ids["contextMap.traceId"] == ["T1", "T2"]
    assert ids["contextMap.correlationID"] == ["C1"]
    assert ids["requestID"] == ["R1"]
    assert ids["sessionID"] == ["S1"]
    assert "contextMap.requestID" not in ids  # absent when no values


def test_extract_correlation_ids_redacts_pii():
    # Defensive: misconfigured emitter logs an email as a "traceId".
    raw = [{"contextMap.traceId": "leak@example.com"}]
    ids = extract_correlation_ids(raw)
    assert ids["contextMap.traceId"] == ["[REDACTED_EMAIL]"]


def test_build_masked_package_includes_correlation_ids():
    hits = [{"contextMap.traceId": "T1"}]
    pkg = build_masked_log_package(
        evidence_session_id="ESESS-1",
        evidence_request_id="EREQ-abc",
        output_profile="default",
        redacted_hits=hits,
        hit_count=1,
        audit_ref="AUD-xyz",
        correlation_ids={"contextMap.traceId": ["T1"]},
    )
    assert pkg.masked_data["correlation_ids"] == {"contextMap.traceId": ["T1"]}
