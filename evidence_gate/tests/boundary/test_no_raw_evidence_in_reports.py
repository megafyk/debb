"""Boundary tests: debug reports must not contain raw sensitive values."""
from __future__ import annotations

from evidence_gate.request_services.report_reviewer import review_report


def _base_report(**overrides):
    report = {
        "ticket_id": "BUG-123",
        "evidence_session_id": "ESESS-1",
        "summary": "Login failures due to phone normalization",
        "services_inspected": ["login-service"],
        "code_paths_inspected": ["src/phone_normalizer.py"],
        "most_likely_root_cause": "Missing leading zero causes lookup failure",
        "confidence": "medium",
        "confidence_rationale": "Consistent with log patterns and code path",
        "evidence_ids": ["EVID-abc123"],
        "audit_refs": ["AUD-def456"],
        "verification_steps": ["Check phone_normalizer.py line 42"],
    }
    report.update(overrides)
    return report


def test_report_with_raw_phone_rejected():
    report = _base_report(summary="Phone +66812345678 fails normalization")
    result = review_report(report)
    assert result.ok is False
    assert any("phone" in i.lower() for i in result.issues)


def test_report_with_raw_email_rejected():
    report = _base_report(summary="User victim@example.com reported failure")
    result = review_report(report)
    assert result.ok is False
    assert any("email" in i.lower() for i in result.issues)


def test_report_with_jwt_rejected():
    report = _base_report(
        summary="Token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9_fakepayload was found",
    )
    result = review_report(report)
    assert result.ok is False
    assert any("jwt" in i.lower() or "token" in i.lower() for i in result.issues)


def test_report_with_credentials_rejected():
    report = _base_report(suggested_fix="Set password=newSecret in config")
    result = review_report(report)
    assert result.ok is False
    assert any("credential" in i.lower() for i in result.issues)


def test_report_with_secure_ref_ok():
    report = _base_report(
        summary="Phone masked as SECURE_VALUE_REF_phone_001 fails normalization",
    )
    result = review_report(report)
    assert result.ok is True
    assert result.issues == []
