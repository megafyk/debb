from __future__ import annotations

from evidence_gate.request_services.report_reviewer import review_report


def _valid_report():
    return {
        "ticket_id": "BUG-123",
        "evidence_session_id": "ESESS-1",
        "summary": "Login failures due to phone normalization",
        "services_inspected": ["login-service"],
        "code_paths_inspected": ["src/phone_normalizer.py"],
        "most_likely_root_cause": "Missing leading zero in phone normalization causes lookup failure",
        "confidence": "medium",
        "confidence_rationale": "Consistent with log patterns and code path",
        "evidence_ids": ["EVID-abc123"],
        "audit_refs": ["AUD-def456"],
        "verification_steps": ["Check phone_normalizer.py line 42 for leading zero handling"],
    }


def test_valid_report_passes():
    result = review_report(_valid_report())
    assert result.ok is True
    assert result.issues == []


def test_missing_ticket_id_flagged():
    report = _valid_report()
    del report["ticket_id"]
    result = review_report(report)
    assert result.ok is False
    assert any("missing required field" in i for i in result.issues)


def test_missing_evidence_ids_flagged():
    report = _valid_report()
    report["evidence_ids"] = []
    result = review_report(report)
    assert result.ok is False
    assert any("no evidence_ids cited" in i for i in result.issues)


def test_missing_verification_steps_flagged():
    report = _valid_report()
    report["verification_steps"] = []
    result = review_report(report)
    assert result.ok is False
    assert any("no verification_steps provided" in i for i in result.issues)


def test_invalid_confidence_flagged():
    report = _valid_report()
    report["confidence"] = "absolute"
    result = review_report(report)
    assert result.ok is False
    assert any("invalid confidence" in i for i in result.issues)


def test_email_in_report_flagged():
    report = _valid_report()
    report["summary"] = "User user@test.com reported login failures"
    result = review_report(report)
    assert result.ok is False
    assert any("raw email detected" in i for i in result.issues)


def test_phone_in_report_flagged():
    report = _valid_report()
    report["most_likely_root_cause"] = "Phone +66812345678 fails normalization"
    result = review_report(report)
    assert result.ok is False
    assert any("raw phone number detected" in i for i in result.issues)


def test_credential_in_report_flagged():
    report = _valid_report()
    report["suggested_fix"] = "Update config where password=secret123"
    result = review_report(report)
    assert result.ok is False
    assert any("credential assignment detected" in i for i in result.issues)


def test_jwt_in_report_flagged():
    report = _valid_report()
    report["summary"] = "Token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9_fakepayload found in logs"
    result = review_report(report)
    assert result.ok is False
    assert any("JWT/token detected" in i for i in result.issues)


def test_overstatement_flagged():
    report = _valid_report()
    report["most_likely_root_cause"] = "The AI proved the root cause is in normalizer"
    result = review_report(report)
    assert result.ok is False
    assert any("overstatement" in i for i in result.issues)
