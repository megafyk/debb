"""Boundary tests: unsafe query plans must always be rejected."""

import tempfile
from pathlib import Path

from evidence_gate.audit.audit_logger import AuditLogger
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


def _base_quickwit():
    return {
        "evidence_session_id": "ESESS-1",
        "service": "login-service",
        "index_hint": "login-service-prod",
        "time_window": {"start": "2026-01-01T00:00:00+00:00", "end": "2026-01-01T02:00:00+00:00"},
        "query_intent": "Find errors",
        "filters": [{"field": "service", "op": "=", "value": "login-service"}],
        "fields_requested": ["timestamp"],
        "max_hits": 50,
    }


def test_rejects_plan_with_raw_email():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(Path(tmp))
        plan = _base_quickwit()
        plan["filters"].append({"field": "user", "op": "=", "value": "attacker@evil.com"})
        result = validate_quickwit_request(plan, "ESESS-1", store)
        assert not result.accepted


def test_rejects_plan_with_raw_phone():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(Path(tmp))
        plan = _base_quickwit()
        plan["filters"].append({"field": "phone", "op": "=", "value": "+66812345678"})
        result = validate_quickwit_request(plan, "ESESS-1", store)
        assert not result.accepted


def test_rejects_plan_with_jwt():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(Path(tmp))
        plan = _base_quickwit()
        plan["query_intent"] = "Find logs with eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0"
        result = validate_quickwit_request(plan, "ESESS-1", store)
        assert not result.accepted


def test_rejects_metabase_drop_table():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(Path(tmp))
        plan = {
            "evidence_session_id": "ESESS-1",
            "service": "x",
            "entity": "account",
            "query_intent": "Delete everything",
            "facts_requested": ["gone"],
            "sql_candidate": "DROP TABLE accounts; --",
        }
        result = validate_metabase_request(plan, "ESESS-1", store)
        assert not result.accepted


def test_rejects_metabase_select_star():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(Path(tmp))
        plan = {
            "evidence_session_id": "ESESS-1",
            "service": "x",
            "entity": "account",
            "query_intent": "Dump everything",
            "facts_requested": ["all"],
            "sql_candidate": "SELECT * FROM accounts",
        }
        result = validate_metabase_request(plan, "ESESS-1", store)
        assert not result.accepted


def test_accepts_plan_with_secure_value_ref():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(Path(tmp))
        plan = _base_quickwit()
        plan["filters"].append({"field": "phone", "op": "matches_sensitive_ref", "value_ref": "SECURE_VALUE_REF_phone_001"})
        result = validate_quickwit_request(plan, "ESESS-1", store)
        assert result.accepted
