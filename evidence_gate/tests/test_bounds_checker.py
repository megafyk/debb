from evidence_gate.request_services.bounds_checker import check_metabase_bounds, check_quickwit_bounds


def _valid_quickwit_plan():
    return {
        "from": "2026-01-01T00:00:00+00:00",
        "to": "2026-01-01T02:00:00+00:00",
        "max_hits": 100,
        "filters": [{"field": "service", "op": "=", "value": "login-service"}],
    }


def test_valid_plan_passes():
    result = check_quickwit_bounds(_valid_quickwit_plan())
    assert result.ok
    assert not result.narrowed


def test_narrows_wide_time_window():
    plan = _valid_quickwit_plan()
    plan["from"] = "2026-01-01T00:00:00+00:00"
    plan["to"] = "2026-01-03T00:00:00+00:00"  # 48h
    result = check_quickwit_bounds(plan)
    assert result.ok
    assert result.narrowed
    assert any("time_window" in n for n in result.narrowing_applied)


def test_narrows_high_max_hits():
    plan = _valid_quickwit_plan()
    plan["max_hits"] = 999
    result = check_quickwit_bounds(plan)
    assert result.ok
    assert result.narrowed
    assert any("max_hits" in n for n in result.narrowing_applied)


def test_rejects_no_filters():
    plan = _valid_quickwit_plan()
    plan["filters"] = []
    result = check_quickwit_bounds(plan)
    assert not result.ok
    assert "filter" in result.rejection_reason


def test_rejects_invalid_time_format():
    plan = _valid_quickwit_plan()
    plan["from"] = "not-a-date"
    plan["to"] = "also-not"
    result = check_quickwit_bounds(plan)
    assert not result.ok
    assert "format" in result.rejection_reason


def test_rejects_end_before_start():
    plan = _valid_quickwit_plan()
    plan["from"] = "2026-01-02T00:00:00+00:00"
    plan["to"] = "2026-01-01T00:00:00+00:00"
    result = check_quickwit_bounds(plan)
    assert not result.ok
    assert "after from" in result.rejection_reason


def test_metabase_passes_valid():
    plan = {"entity": "account", "facts_requested": ["exists"], "params": [{"name": "id"}]}
    result = check_metabase_bounds(plan)
    assert result.ok


def test_metabase_rejects_unparameterized_sql():
    plan = {"sql_candidate": "SELECT status FROM account WHERE id = 1", "facts_requested": ["status"]}
    result = check_metabase_bounds(plan)
    assert not result.ok
    assert "params" in result.rejection_reason
