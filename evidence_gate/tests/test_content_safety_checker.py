from evidence_gate.request_services.content_safety_checker import check_plan_safety


def test_clean_plan_passes():
    plan = {
        "service": "login-service",
        "query_intent": "Find login failures",
        "filters": [{"field": "error_code", "op": "=", "value": "ACCOUNT_LOOKUP_FAILED"}],
    }
    result = check_plan_safety(plan)
    assert result.ok


def test_rejects_raw_email():
    plan = {"query_intent": "Find records for user@example.com"}
    result = check_plan_safety(plan)
    assert not result.ok
    assert any("email" in v for v in result.violations)


def test_rejects_raw_phone():
    plan = {"filters": [{"field": "phone", "value": "+66812345678"}]}
    result = check_plan_safety(plan)
    assert not result.ok
    assert any("phone" in v for v in result.violations)


def test_rejects_jwt_token():
    plan = {"query_intent": "Find logs with eyJhbGciOiJIUzI1NiJ9xyz"}
    result = check_plan_safety(plan)
    assert not result.ok
    assert any("JWT" in v or "token" in v for v in result.violations)


def test_rejects_mutating_sql_in_sql_candidate():
    plan = {"sql_candidate": "DELETE FROM accounts WHERE id = 1"}
    result = check_plan_safety(plan)
    assert not result.ok
    assert any("mutating" in v for v in result.violations)


def test_rejects_mutating_sql():
    plan = {"sql_candidate": "DROP TABLE accounts"}
    result = check_plan_safety(plan)
    assert not result.ok
    assert any("mutating" in v for v in result.violations)


def test_rejects_credential_in_value():
    plan = {"filters": [{"field": "config", "value": "password: secret123"}]}
    result = check_plan_safety(plan)
    assert not result.ok
    assert any("credential" in v for v in result.violations)


def test_allows_secure_value_refs():
    plan = {
        "service": "login-service",
        "filters": [{"field": "phone", "op": "matches_sensitive_ref", "value_ref": "SECURE_VALUE_REF_phone_001"}],
    }
    result = check_plan_safety(plan)
    assert result.ok
