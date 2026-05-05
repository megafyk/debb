from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from evidence_gate.config import Settings
from evidence_gate.audit_logger import AuditLogger
from evidence_gate.connectors.metabase_connector import MetabaseConnector
from evidence_gate.contracts import MetabaseQueryPlan
from evidence_gate.storage.sensitive_value_store import SensitiveValueStore
from evidence_gate.storage.jsonl_event_store import JsonlEventStore


def _make_plan(**overrides) -> MetabaseQueryPlan:
    defaults = dict(
        type="metabase_query_plan",
        evidence_session_id="ESESS-1",
        service="login-service",
        entity="account",
        query_intent="Check account status",
        facts_requested=["account_exists", "account_status"],
        params=[
            {"name": "phone_number", "value": "hashed_phone"},
            {"name": "tenant_salt", "value": "salt123"},
        ],
    )
    defaults.update(overrides)
    return MetabaseQueryPlan(**defaults)


def _setup(tmp_path: Path):
    settings = Settings(metabase_url="", metabase_username="", metabase_password="")
    sensitive_store = SensitiveValueStore(tmp_path)
    audit_logger = AuditLogger(JsonlEventStore(tmp_path / "audit.jsonl"))
    connector = MetabaseConnector(settings, sensitive_store, audit_logger)
    return connector, settings, sensitive_store, audit_logger


def test_fixture_mode_account():
    with tempfile.TemporaryDirectory() as tmp:
        connector, _, _, _ = _setup(Path(tmp))
        plan = _make_plan()
        rows = asyncio.run(connector.execute(plan, "ESESS-1"))
        assert len(rows) == 1
        assert rows[0]["status"] == "active"


def test_fixture_mode_login_attempt():
    with tempfile.TemporaryDirectory() as tmp:
        connector, _, _, _ = _setup(Path(tmp))
        plan = _make_plan(
            entity="login_attempt",
            facts_requested=["error_distribution"],
            params=[
                {"name": "service", "value": "login-service"},
                {"name": "since", "value": "2025-01-01"},
                {"name": "until", "value": "2025-01-02"},
            ],
        )
        rows = asyncio.run(connector.execute(plan, "ESESS-1"))
        assert len(rows) == 2
        assert rows[0]["error_code"] == "PHONE_NORMALIZATION_FAILED"


def test_is_live_false_when_no_url():
    with tempfile.TemporaryDirectory() as tmp:
        connector, _, _, _ = _setup(Path(tmp))
        assert connector.is_live is False


def test_is_live_true_when_url_set():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        settings = Settings(metabase_enabled=True, metabase_url="http://localhost:3000", metabase_username="", metabase_password="")
        sensitive_store = SensitiveValueStore(tmp_path)
        audit_logger = AuditLogger(JsonlEventStore(tmp_path / "audit.jsonl"))
        connector = MetabaseConnector(settings, sensitive_store, audit_logger)
        assert connector.is_live is True


def test_no_template_raises():
    with tempfile.TemporaryDirectory() as tmp:
        connector, _, _, _ = _setup(Path(tmp))
        plan = _make_plan(entity="nonexistent", facts_requested=["nope"])
        try:
            asyncio.run(connector.execute(plan, "ESESS-1"))
            assert False, "Should have raised"
        except ValueError as exc:
            assert "No registered template" in str(exc)


def test_bad_params_raises():
    with tempfile.TemporaryDirectory() as tmp:
        connector, _, _, _ = _setup(Path(tmp))
        plan = _make_plan(params=[])  # missing required params
        try:
            asyncio.run(connector.execute(plan, "ESESS-1"))
            assert False, "Should have raised"
        except ValueError as exc:
            assert "resolve" in str(exc).lower()


def test_audit_logged_after_execute():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        event_store = JsonlEventStore(tmp_path / "audit.jsonl")
        audit_logger = AuditLogger(event_store)
        settings = Settings(metabase_url="", metabase_username="", metabase_password="")
        sensitive_store = SensitiveValueStore(tmp_path)
        connector = MetabaseConnector(settings, sensitive_store, audit_logger)

        plan = _make_plan()
        asyncio.run(connector.execute(plan, "ESESS-1"))

        events = event_store.read_all()
        mb_events = [e for e in events if e.get("event_type") == "metabase_query_executed"]
        assert len(mb_events) >= 1
