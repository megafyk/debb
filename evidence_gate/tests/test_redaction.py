from evidence_gate.redaction.jira_redactor import redact_text


def test_redacts_email():
    assert "[REDACTED_EMAIL]" in redact_text("Contact user@example.com for details")


def test_redacts_phone_with_country_code():
    result = redact_text("Call +66812345678")
    assert "[REDACTED_PHONE]" in result


def test_redacts_phone_local():
    result = redact_text("Phone: 081-234-5678")
    assert "[REDACTED_PHONE]" in result


def test_redacts_jwt_like_token():
    # Bare JWT (no "Token:" prefix) should be caught by the token pattern
    result = redact_text("Auth eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc123")
    assert "[REDACTED_TOKEN]" in result


def test_redacts_token_assignment():
    # "Token: <value>" is caught by the credential pattern (case-insensitive match on "token:")
    result = redact_text("Token: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc123")
    assert "[REDACTED_CREDENTIAL]" in result


def test_redacts_password_assignment():
    result = redact_text("password: my_secret_123")
    assert "[REDACTED_CREDENTIAL]" in result


def test_preserves_safe_text():
    text = "Login failed with error code ACCOUNT_LOOKUP_FAILED"
    assert redact_text(text) == text


def test_redacts_multiple_patterns():
    text = "User user@test.com called from +66812345678 with password: secret123"
    result = redact_text(text)
    assert "[REDACTED_EMAIL]" in result
    assert "[REDACTED_PHONE]" in result
    assert "[REDACTED_CREDENTIAL]" in result
    assert "user@test.com" not in result
