"""End-to-end eval: full debugging flow from ticket to report using fixture connectors."""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from evidence_gate.config import Settings
from evidence_gate.audit_logger import AuditLogger
from evidence_gate.connectors.jira_connector import JiraConnector
from evidence_gate.connectors.metabase_connector import MetabaseConnector
from evidence_gate.connectors.quickwit_connector import QuickwitConnector
from evidence_gate.mcp_server.tools import (
    _create_quickwit_evidence_request,
    _get_masked_evidence_package,
    _start_debugging_session,
    _submit_debug_report,
)
from evidence_gate.storage.evidence_session_store import EvidenceSessionStore
from evidence_gate.storage.sensitive_value_store import SensitiveValueStore
from evidence_gate.storage.evidence_request_store import EvidenceRequestStore
from evidence_gate.storage.json_store import JsonStore
from evidence_gate.storage.jsonl_event_store import JsonlEventStore
from evidence_gate.storage.masked_package_store import MaskedPackageStore
from evidence_gate.storage.raw_evidence_store import RawEvidenceStore


def _make_all_deps(tmp_path: Path):
    test_settings = Settings(
        quickwit_url="", quickwit_username="", quickwit_password="",
        metabase_url="", metabase_username="", metabase_password="",
    )
    session_store = EvidenceSessionStore(tmp_path)
    sensitive_store = SensitiveValueStore(tmp_path)
    event_store = JsonlEventStore(tmp_path / "audit" / "events.jsonl")
    audit_logger = AuditLogger(event_store)
    jira = JiraConnector()
    request_store = EvidenceRequestStore(
        JsonStore(tmp_path, "evidence_requests"), audit_logger,
    )
    quickwit = QuickwitConnector(test_settings, sensitive_store, audit_logger)
    metabase = MetabaseConnector(test_settings, sensitive_store, audit_logger)
    raw_store = RawEvidenceStore(tmp_path)
    masked_store = MaskedPackageStore(tmp_path)
    report_store = JsonStore(tmp_path, "reports")
    return {
        "session_store": session_store,
        "sensitive_store": sensitive_store,
        "audit_logger": audit_logger,
        "jira": jira,
        "request_store": request_store,
        "quickwit": quickwit,
        "metabase": metabase,
        "raw_store": raw_store,
        "masked_store": masked_store,
        "report_store": report_store,
    }


def test_full_debugging_flow():
    with tempfile.TemporaryDirectory() as tmp:
        d = _make_all_deps(Path(tmp))

        # Step 1: Start debugging session
        session_result = asyncio.run(
            _start_debugging_session(
                "BUG-123", "", "",
                d["session_store"], d["sensitive_store"], d["audit_logger"], d["jira"],
            )
        )
        session_data = json.loads(session_result[0].text)
        evidence_session_id = session_data["evidence_session_id"]
        assert evidence_session_id.startswith("ESESS-")
        audit_refs_session = session_data.get("audit_refs", [])

        # Step 2: Submit a Quickwit query plan
        qw_plan = {
            "type": "quickwit_query_plan",
            "evidence_session_id": evidence_session_id,
            "service": "login-service",
            "datasource_uid": "login-service-prod",
            "from": "2026-01-01T00:00:00+00:00",
            "to": "2026-01-01T02:00:00+00:00",
            "query_intent": "Find login failures",
            "filters": [{"field": "error_code", "op": "=", "value": "ACCOUNT_LOOKUP_FAILED"}],
            "fields_requested": ["timestamp", "error_code"],
            "max_hits": 100,
        }
        qw_result = asyncio.run(
            _create_quickwit_evidence_request(
                qw_plan,
                d["request_store"], d["quickwit"], d["raw_store"], d["masked_store"], d["audit_logger"],
            )
        )
        qw_data = json.loads(qw_result[0].text)
        assert qw_data["accepted"] is True
        evidence_id = qw_data["evidence_id"]
        assert evidence_id.startswith("EVID-")

        # Step 3: Get masked evidence package
        pkg_result = asyncio.run(
            _get_masked_evidence_package(evidence_id, d["masked_store"]),
        )
        pkg_data = json.loads(pkg_result[0].text)
        assert len(pkg_data["masked_data"]["hits"]) > 0

        # Step 4: Submit a debug report referencing the evidence
        report_data = {
            "ticket_id": "BUG-123",
            "evidence_session_id": evidence_session_id,
            "summary": "Login failures due to phone normalization",
            "services_inspected": ["login-service"],
            "code_paths_inspected": ["src/phone_normalizer.py"],
            "most_likely_root_cause": "Missing leading zero in phone normalization causes lookup failure",
            "confidence": "medium",
            "confidence_rationale": "Consistent with log patterns and code path",
            "evidence_ids": [evidence_id],
            "audit_refs": audit_refs_session[:1] if audit_refs_session else ["AUD-placeholder"],
            "verification_steps": ["Check phone_normalizer.py line 42 for leading zero handling"],
        }
        report_result = asyncio.run(
            _submit_debug_report(report_data, d["report_store"], d["audit_logger"]),
        )
        report_data_resp = json.loads(report_result[0].text)
        assert report_data_resp["accepted"] is True
        assert report_data_resp["report_id"].startswith("RPT-")
