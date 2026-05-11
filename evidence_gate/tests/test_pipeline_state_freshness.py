"""Pipeline must surface the post-transition state to MCP callers."""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from evidence_gate.audit_logger import AuditLogger
from evidence_gate.connectors.metabase_connector import MetabaseConnector
from evidence_gate.connectors.quickwit_connector import QuickwitConnector
from evidence_gate.config import Settings
from evidence_gate.mcp_server.tools import (
    _create_metabase_evidence_request,
    _create_quickwit_evidence_request,
)
from evidence_gate.request_services.request_pipeline import (
    validate_metabase_request,
    validate_quickwit_request,
)
from evidence_gate.storage.evidence_request_store import EvidenceRequestStore
from evidence_gate.storage.json_store import JsonStore
from evidence_gate.storage.jsonl_event_store import JsonlEventStore
from evidence_gate.contracts import EvidenceSession
from evidence_gate.storage.debug_report_evidence_store import DebugReportEvidenceStore
from evidence_gate.storage.evidence_session_store import EvidenceSessionStore
from evidence_gate.storage.masked_package_store import MaskedPackageStore
from evidence_gate.storage.raw_evidence_store import RawEvidenceStore
from evidence_gate.storage.sensitive_value_store import SensitiveValueStore


def _make_deps(tmp_path: Path):
    json_store = JsonStore(tmp_path, "requests")
    audit_logger = AuditLogger(JsonlEventStore(tmp_path / "audit.jsonl"))
    request_store = EvidenceRequestStore(json_store, audit_logger)
    settings = Settings(quickwit_url="", quickwit_username="", quickwit_password="",
                        metabase_url="", metabase_username="", metabase_password="")
    sensitive_store = SensitiveValueStore(tmp_path)
    quickwit = QuickwitConnector(settings, sensitive_store, audit_logger)
    metabase = MetabaseConnector(settings, sensitive_store, audit_logger)
    raw_store = RawEvidenceStore(tmp_path)
    masked_store = MaskedPackageStore(tmp_path)
    dr_store = DebugReportEvidenceStore(tmp_path)
    session_store = EvidenceSessionStore(tmp_path)
    session_store.save(EvidenceSession(
        evidence_session_id="ESESS-1", ticket_id="BUG-1",
        trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
    ))
    return request_store, quickwit, metabase, raw_store, masked_store, dr_store, session_store, audit_logger


def _quickwit_plan(**overrides):
    plan = {
        "type": "quickwit_query_plan",
        "evidence_session_id": "ESESS-1",
        "service": "login-service",
        "datasource_uid": "login-service-prod",
        "from": "2026-01-01T00:00:00+00:00",
        "to": "2026-01-01T02:00:00+00:00",
        "query_intent": "Find login failures",
        "filters": [{"field": "error_code", "op": "=", "value": "ACCOUNT_LOOKUP_FAILED"}],
        "fields_requested": ["timestamp", "error_code"],
        "max_hits": 100,
    }
    plan.update(overrides)
    return plan


def test_validate_quickwit_returns_request_with_rejected_state_after_schema_failure():
    with tempfile.TemporaryDirectory() as tmp:
        store, *_ = _make_deps(Path(tmp))
        plan = _quickwit_plan()
        del plan["service"]
        result = validate_quickwit_request(plan, "ESESS-1", store)
        assert not result.accepted
        assert result.request.state == "rejected"
        assert result.request.rejection_reason


def test_validate_quickwit_returns_request_with_rejected_state_after_safety_failure():
    with tempfile.TemporaryDirectory() as tmp:
        store, *_ = _make_deps(Path(tmp))
        plan = _quickwit_plan(query_intent="Find records for bad@actor.com")
        result = validate_quickwit_request(plan, "ESESS-1", store)
        assert not result.accepted
        assert result.request.state == "rejected"


def test_validate_quickwit_returns_request_with_bounded_state_when_accepted():
    with tempfile.TemporaryDirectory() as tmp:
        store, *_ = _make_deps(Path(tmp))
        result = validate_quickwit_request(_quickwit_plan(), "ESESS-1", store)
        assert result.accepted
        assert result.request.state == "bounded"


def test_validate_metabase_returns_rejected_state_after_safety_failure():
    with tempfile.TemporaryDirectory() as tmp:
        store, *_ = _make_deps(Path(tmp))
        plan = {
            "type": "metabase_query_plan",
            "evidence_session_id": "ESESS-1",
            "service": "x",
            "entity": "account",
            "query_intent": "Dump all",
            "facts_requested": ["all"],
            "sql_candidate": "SELECT * FROM accounts",
        }
        result = validate_metabase_request(plan, "ESESS-1", store)
        assert not result.accepted
        assert result.request.state == "rejected"


def test_mcp_quickwit_rejection_response_carries_rejected_state():
    """Regression: rejection responses used to leak the initial 'created' state."""
    with tempfile.TemporaryDirectory() as tmp:
        store, qw, _mb, raw, masked, dr, sess, audit = _make_deps(Path(tmp))
        plan = _quickwit_plan(query_intent="Find records for bad@actor.com")
        result = asyncio.run(_create_quickwit_evidence_request(
            plan, store, qw, raw, masked, dr, sess, audit,
        ))
        data = json.loads(result[0].text)
        assert data["accepted"] is False
        assert data["state"] == "rejected"


def test_mcp_metabase_rejection_response_carries_rejected_state():
    with tempfile.TemporaryDirectory() as tmp:
        store, _qw, mb, raw, masked, dr, sess, audit = _make_deps(Path(tmp))
        plan = {
            "type": "metabase_query_plan",
            "evidence_session_id": "ESESS-1",
            "service": "x",
            "entity": "account",
            "query_intent": "Drop everything",
            "facts_requested": ["all"],
            "sql_candidate": "DROP TABLE accounts",
        }
        result = asyncio.run(_create_metabase_evidence_request(
            plan, store, mb, raw, masked, dr, sess, audit,
        ))
        data = json.loads(result[0].text)
        assert data["accepted"] is False
        assert data["state"] == "rejected"
