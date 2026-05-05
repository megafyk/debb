from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from evidence_gate.config import Settings
from evidence_gate.audit_logger import AuditLogger
from evidence_gate.connectors.quickwit_connector import QuickwitConnector
from evidence_gate.contracts import QuickwitQueryPlan, QueryFilter, TimeWindow
from evidence_gate.storage.sensitive_value_store import SensitiveValueStore
from evidence_gate.storage.jsonl_event_store import JsonlEventStore


def _make_plan(**overrides: object) -> QuickwitQueryPlan:
    defaults = dict(
        type="quickwit_query_plan",
        evidence_session_id="ESESS-1",
        service="login-service",
        index_hint="login-service-prod",
        time_window=TimeWindow(start="2026-01-01T00:00:00+00:00", end="2026-01-01T02:00:00+00:00"),
        query_intent="Find login failures",
        filters=[QueryFilter(field="error_code", op="=", value="ACCOUNT_LOOKUP_FAILED")],
        fields_requested=["timestamp", "error_code", "trace_id"],
        max_hits=100,
    )
    defaults.update(overrides)
    return QuickwitQueryPlan(**defaults)


def _setup(tmp_path: Path):
    settings = Settings(quickwit_url="", quickwit_username="", quickwit_password="")
    sensitive_store = SensitiveValueStore(tmp_path)
    audit_logger = AuditLogger(JsonlEventStore(tmp_path / "audit.jsonl"))
    connector = QuickwitConnector(settings, sensitive_store, audit_logger)
    return connector, settings, sensitive_store, audit_logger


def test_fixture_mode_returns_hits():
    with tempfile.TemporaryDirectory() as tmp:
        connector, _, _, _ = _setup(Path(tmp))
        plan = _make_plan()
        hits = asyncio.run(connector.execute(plan, "ESESS-1"))
        assert len(hits) == 3
        for hit in hits:
            for field in plan.fields_requested:
                assert field in hit


def test_is_live_false_when_no_url():
    with tempfile.TemporaryDirectory() as tmp:
        connector, _, _, _ = _setup(Path(tmp))
        assert connector.is_live is False


def test_is_live_true_when_url_set():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        settings = Settings(quickwit_url="http://localhost:7280", quickwit_username="", quickwit_password="")
        sensitive_store = SensitiveValueStore(tmp_path)
        audit_logger = AuditLogger(JsonlEventStore(tmp_path / "audit.jsonl"))
        connector = QuickwitConnector(settings, sensitive_store, audit_logger)
        assert connector.is_live is True


def test_build_search_body_filters():
    with tempfile.TemporaryDirectory() as tmp:
        connector, _, _, _ = _setup(Path(tmp))
        plan = _make_plan(
            filters=[
                QueryFilter(field="error_code", op="=", value="ACCOUNT_LOOKUP_FAILED"),
                QueryFilter(field="level", op="in", value=["ERROR", "WARN"]),
                QueryFilter(field="message", op="contains", value="timeout"),
            ]
        )
        body = connector._build_search_body(plan, "ESESS-1")
        query = body["query"]
        assert "error_code:ACCOUNT_LOOKUP_FAILED" in query
        assert "level:IN [ERROR WARN]" in query
        assert "message:timeout" in query
        assert " AND " in query


def test_build_search_body_sensitive_ref():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        connector, _, sensitive_store, _ = _setup(tmp_path)
        ref = sensitive_store.store("ESESS-1", "email", "admin@corp.com")
        plan = _make_plan(
            filters=[QueryFilter(field="user_email", op="matches_sensitive_ref", value_ref=ref)]
        )
        body = connector._build_search_body(plan, "ESESS-1")
        assert "admin@corp.com" in body["query"]


def test_audit_logged_after_execute():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        event_store = JsonlEventStore(tmp_path / "audit.jsonl")
        audit_logger = AuditLogger(event_store)
        settings = Settings(quickwit_url="", quickwit_username="", quickwit_password="")
        sensitive_store = SensitiveValueStore(tmp_path)
        connector = QuickwitConnector(settings, sensitive_store, audit_logger)

        plan = _make_plan()
        asyncio.run(connector.execute(plan, "ESESS-1"))

        events = event_store.read_all()
        qw_events = [e for e in events if e.get("event_type") == "quickwit_query_executed"]
        assert len(qw_events) >= 1
