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
    _get_evidence_request_status,
    _get_masked_evidence_package,
)
from evidence_gate.storage.sensitive_value_store import SensitiveValueStore
from evidence_gate.storage.evidence_request_store import EvidenceRequestStore
from evidence_gate.storage.json_store import JsonStore
from evidence_gate.storage.jsonl_event_store import JsonlEventStore
from evidence_gate.storage.masked_package_store import MaskedPackageStore
from evidence_gate.storage.raw_evidence_store import RawEvidenceStore


def _make_deps(tmp_path: Path):
    json_store = JsonStore(tmp_path, "requests")
    audit_logger = AuditLogger(JsonlEventStore(tmp_path / "audit.jsonl"))
    request_store = EvidenceRequestStore(json_store, audit_logger)
    test_settings = Settings(
        quickwit_url="", quickwit_username="", quickwit_password="",
        metabase_url="", metabase_username="", metabase_password="",
    )
    sensitive_store = SensitiveValueStore(tmp_path)
    quickwit_connector = QuickwitConnector(test_settings, sensitive_store, audit_logger)
    metabase_connector = MetabaseConnector(test_settings, sensitive_store, audit_logger)
    raw_store = RawEvidenceStore(tmp_path)
    masked_store = MaskedPackageStore(tmp_path)
    return request_store, quickwit_connector, metabase_connector, raw_store, masked_store, audit_logger


def _valid_quickwit_plan():
    return {
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


def test_create_quickwit_request_accepted():
    with tempfile.TemporaryDirectory() as tmp:
        store, qw, _mb, raw, masked, audit = _make_deps(Path(tmp))
        result = asyncio.run(_create_quickwit_evidence_request(
            _valid_quickwit_plan(), store, qw, raw, masked, audit,
        ))
        data = json.loads(result[0].text)
        assert data["accepted"] is True
        assert data["evidence_request_id"].startswith("EREQ-")
        assert data["state"] == "masked_package_ready"
        assert "evidence_id" in data


def test_create_quickwit_request_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        store, qw, _mb, raw, masked, audit = _make_deps(Path(tmp))
        plan = _valid_quickwit_plan()
        plan["query_intent"] = "Find records for user@evil.com"
        result = asyncio.run(_create_quickwit_evidence_request(
            plan, store, qw, raw, masked, audit,
        ))
        data = json.loads(result[0].text)
        assert data["accepted"] is False
        assert "rejection_reason" in data


def test_create_request_missing_session_id():
    with tempfile.TemporaryDirectory() as tmp:
        store, qw, _mb, raw, masked, audit = _make_deps(Path(tmp))
        result = asyncio.run(_create_quickwit_evidence_request(
            {"service": "x"}, store, qw, raw, masked, audit,
        ))
        data = json.loads(result[0].text)
        assert "error" in data


def test_get_evidence_request_status():
    with tempfile.TemporaryDirectory() as tmp:
        store, qw, _mb, raw, masked, audit = _make_deps(Path(tmp))
        create_result = asyncio.run(_create_quickwit_evidence_request(
            _valid_quickwit_plan(), store, qw, raw, masked, audit,
        ))
        req_id = json.loads(create_result[0].text)["evidence_request_id"]

        status_result = asyncio.run(_get_evidence_request_status(req_id, store))
        data = json.loads(status_result[0].text)
        assert data["evidence_request_id"] == req_id
        assert data["state"] == "masked_package_ready"


def test_get_masked_evidence_package():
    with tempfile.TemporaryDirectory() as tmp:
        store, qw, _mb, raw, masked, audit = _make_deps(Path(tmp))
        create_result = asyncio.run(_create_quickwit_evidence_request(
            _valid_quickwit_plan(), store, qw, raw, masked, audit,
        ))
        data = json.loads(create_result[0].text)
        evidence_id = data["evidence_id"]

        pkg_result = asyncio.run(_get_masked_evidence_package(evidence_id, masked))
        pkg_data = json.loads(pkg_result[0].text)
        assert pkg_data["evidence_id"] == evidence_id
        assert pkg_data["source_type"] == "quickwit_logs"
        assert len(pkg_data["masked_data"]["hits"]) == 3  # fixture returns 3 hits


def test_get_status_missing_request():
    with tempfile.TemporaryDirectory() as tmp:
        store, _, _, _, _, _ = _make_deps(Path(tmp))
        result = asyncio.run(_get_evidence_request_status("EREQ-nonexistent", store))
        data = json.loads(result[0].text)
        assert "error" in data


# --- Metabase MCP tests ---

def _valid_metabase_plan():
    return {
        "type": "metabase_query_plan",
        "evidence_session_id": "ESESS-1",
        "service": "account-service",
        "entity": "login_attempt",
        "query_intent": "Check login error distribution",
        "sql_candidate": "",
        "params": [
            {"name": "service", "value": "login-service"},
            {"name": "since", "value": "2026-01-01"},
            {"name": "until", "value": "2026-01-02"},
        ],
        "facts_requested": ["error_distribution", "total_failures"],
    }


def test_create_metabase_request_accepted():
    with tempfile.TemporaryDirectory() as tmp:
        store, _qw, mb, raw, masked, audit = _make_deps(Path(tmp))
        result = asyncio.run(_create_metabase_evidence_request(
            _valid_metabase_plan(), store, mb, raw, masked, audit,
        ))
        data = json.loads(result[0].text)
        assert data["accepted"] is True
        assert data["state"] == "masked_package_ready"
        assert "evidence_id" in data


def test_create_metabase_request_with_select_star_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        store, _qw, mb, raw, masked, audit = _make_deps(Path(tmp))
        plan = _valid_metabase_plan()
        plan["sql_candidate"] = "SELECT * FROM accounts"
        result = asyncio.run(_create_metabase_evidence_request(
            plan, store, mb, raw, masked, audit,
        ))
        data = json.loads(result[0].text)
        assert data["accepted"] is False


def test_metabase_masked_package_has_diagnostic_features():
    with tempfile.TemporaryDirectory() as tmp:
        store, _qw, mb, raw, masked, audit = _make_deps(Path(tmp))
        result = asyncio.run(_create_metabase_evidence_request(
            _valid_metabase_plan(), store, mb, raw, masked, audit,
        ))
        data = json.loads(result[0].text)
        evidence_id = data["evidence_id"]

        pkg_result = asyncio.run(_get_masked_evidence_package(evidence_id, masked))
        pkg_data = json.loads(pkg_result[0].text)
        assert pkg_data["source_type"] == "metabase_query"
        assert len(pkg_data["diagnostic_features"]) > 0
