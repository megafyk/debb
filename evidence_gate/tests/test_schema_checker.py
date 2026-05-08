from evidence_gate.request_services.schema_checker import check_metabase_plan, check_quickwit_plan


def _valid_quickwit_plan():
    return {
        "evidence_session_id": "ESESS-1",
        "service": "login-service",
        "datasource_uid": "login-service-prod",
        "from": "2026-01-01T00:00:00Z",
        "to": "2026-01-01T01:00:00Z",
        "query_intent": "Find login failures",
        "filters": [{"field": "service", "op": "=", "value": "login-service"}],
        "fields_requested": ["timestamp", "error_code"],
        "max_hits": 100,
    }


def test_valid_quickwit_plan_passes():
    result = check_quickwit_plan(_valid_quickwit_plan())
    assert result.ok
    assert result.errors == []


def test_missing_service_fails():
    plan = _valid_quickwit_plan()
    del plan["service"]
    result = check_quickwit_plan(plan)
    assert not result.ok
    assert any("service" in e for e in result.errors)


def test_missing_from_fails():
    plan = _valid_quickwit_plan()
    del plan["from"]
    result = check_quickwit_plan(plan)
    assert not result.ok
    assert any("from" in e for e in result.errors)


def test_missing_to_fails():
    plan = _valid_quickwit_plan()
    del plan["to"]
    result = check_quickwit_plan(plan)
    assert not result.ok
    assert any("to" in e for e in result.errors)


def test_invalid_max_hits_fails():
    plan = _valid_quickwit_plan()
    plan["max_hits"] = 5000
    result = check_quickwit_plan(plan)
    assert not result.ok
    assert any("max_hits" in e for e in result.errors)


def test_missing_filters_fails():
    plan = _valid_quickwit_plan()
    plan["filters"] = []
    result = check_quickwit_plan(plan)
    assert not result.ok


def _valid_metabase_plan():
    return {
        "evidence_session_id": "ESESS-1",
        "service": "account-service",
        "entity": "account",
        "query_intent": "Check account status",
        "facts_requested": ["account_exists"],
    }


def test_valid_metabase_plan_passes():
    result = check_metabase_plan(_valid_metabase_plan())
    assert result.ok


def test_metabase_missing_entity_fails():
    plan = _valid_metabase_plan()
    del plan["entity"]
    result = check_metabase_plan(plan)
    assert not result.ok
    assert any("entity" in e for e in result.errors)
