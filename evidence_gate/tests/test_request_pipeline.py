import tempfile
from pathlib import Path

from evidence_gate.audit_logger import AuditLogger
from evidence_gate.request_services.request_pipeline import (
    validate_metabase_request,
    validate_quickwit_request,
)
from evidence_gate.storage.evidence_request_store import EvidenceRequestStore
from evidence_gate.storage.json_store import JsonStore
from evidence_gate.storage.jsonl_event_store import JsonlEventStore


def _make_store(tmp_path: Path):
    json_store = JsonStore(tmp_path, "requests")
    audit_logger = AuditLogger(JsonlEventStore(tmp_path / "audit.jsonl"))
    return EvidenceRequestStore(json_store, audit_logger)


def _valid_quickwit_plan():
    return {
        "type": "quickwit_query_plan",
        "evidence_session_id": "ESESS-1",
        "service": "login-service",
        "index_hint": "login-service-prod",
        "time_window": {"start": "2026-01-01T00:00:00+00:00", "end": "2026-01-01T02:00:00+00:00"},
        "query_intent": "Find login failures",
        "filters": [{"field": "error_code", "op": "=", "value": "ACCOUNT_LOOKUP_FAILED"}],
        "fields_requested": ["timestamp", "error_code", "trace_id"],
        "max_hits": 100,
    }


def test_valid_quickwit_accepted():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(Path(tmp))
        result = validate_quickwit_request(_valid_quickwit_plan(), "ESESS-1", store)
        assert result.accepted
        # The store holds the authoritative state; the in-memory request is stale
        persisted = store.get(result.request.evidence_request_id)
        assert persisted.state == "bounded"


def test_quickwit_missing_service_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(Path(tmp))
        plan = _valid_quickwit_plan()
        del plan["service"]
        result = validate_quickwit_request(plan, "ESESS-1", store)
        assert not result.accepted
        assert "schema" in result.rejection_reason
        persisted = store.get(result.request.evidence_request_id)
        assert persisted.state == "rejected"


def test_quickwit_with_raw_email_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(Path(tmp))
        plan = _valid_quickwit_plan()
        plan["query_intent"] = "Find records for bad@actor.com"
        result = validate_quickwit_request(plan, "ESESS-1", store)
        assert not result.accepted
        assert "safety" in result.rejection_reason


def test_quickwit_overbroad_narrowed():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(Path(tmp))
        plan = _valid_quickwit_plan()
        plan["time_window"] = {"start": "2026-01-01T00:00:00+00:00", "end": "2026-01-03T00:00:00+00:00"}
        plan["max_hits"] = 999
        result = validate_quickwit_request(plan, "ESESS-1", store)
        assert result.accepted
        assert len(result.narrowing_applied) > 0
        # Narrowing must be persisted on the request plan (not just the audit string)
        persisted = store.get(result.request.evidence_request_id)
        assert persisted.plan["max_hits"] == 500
        assert persisted.plan["time_window"]["end"] == "2026-01-03T00:00:00+00:00"
        # 24h window from end
        assert persisted.plan["time_window"]["start"] == "2026-01-02T00:00:00+00:00"


def _valid_metabase_plan():
    return {
        "type": "metabase_query_plan",
        "evidence_session_id": "ESESS-1",
        "service": "account-service",
        "entity": "account",
        "query_intent": "Check account status",
        "facts_requested": ["account_exists", "is_locked"],
    }


def test_valid_metabase_accepted():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(Path(tmp))
        result = validate_metabase_request(_valid_metabase_plan(), "ESESS-1", store)
        assert result.accepted


def test_metabase_select_star_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(Path(tmp))
        plan = _valid_metabase_plan()
        plan["sql_candidate"] = "SELECT * FROM accounts"
        result = validate_metabase_request(plan, "ESESS-1", store)
        assert not result.accepted
        assert "safety" in result.rejection_reason or "bounds" in result.rejection_reason


def test_metabase_drop_table_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(Path(tmp))
        plan = _valid_metabase_plan()
        plan["sql_candidate"] = "DROP TABLE accounts"
        result = validate_metabase_request(plan, "ESESS-1", store)
        assert not result.accepted
