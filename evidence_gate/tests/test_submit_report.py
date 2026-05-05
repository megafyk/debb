from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from evidence_gate.audit_logger import AuditLogger
from evidence_gate.contracts import DebugReport
from evidence_gate.mcp_server.tools import _submit_debug_report
from evidence_gate.storage.json_store import JsonStore
from evidence_gate.storage.jsonl_event_store import JsonlEventStore


def _make_deps(tmp_path: Path):
    audit_path = tmp_path / "audit" / "events.jsonl"
    event_store = JsonlEventStore(audit_path)
    audit_logger = AuditLogger(event_store)
    report_store = JsonStore(tmp_path, "reports")
    return report_store, audit_logger, event_store, audit_path


def _valid_report():
    return {
        "ticket_id": "BUG-123",
        "evidence_session_id": "ESESS-1",
        "summary": "Login failures due to phone normalization",
        "services_inspected": ["login-service"],
        "code_paths_inspected": ["src/phone_normalizer.py"],
        "most_likely_root_cause": "Missing leading zero causes lookup failure",
        "confidence": "medium",
        "confidence_rationale": "Consistent with log patterns and code path",
        "evidence_ids": ["EVID-abc123"],
        "audit_refs": ["AUD-def456"],
        "verification_steps": ["Check phone_normalizer.py line 42"],
    }


def test_submit_valid_report_accepted():
    with tempfile.TemporaryDirectory() as tmp:
        report_store, audit_logger, _, _ = _make_deps(Path(tmp))
        result = asyncio.run(_submit_debug_report(_valid_report(), report_store, audit_logger))
        data = json.loads(result[0].text)
        assert data["accepted"] is True
        assert data["report_id"].startswith("RPT-")


def test_submit_report_with_pii_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        report_store, audit_logger, _, _ = _make_deps(Path(tmp))
        report = _valid_report()
        report["summary"] = "User user@test.com has login issues"
        result = asyncio.run(_submit_debug_report(report, report_store, audit_logger))
        data = json.loads(result[0].text)
        assert data["accepted"] is False
        assert len(data["issues"]) > 0


def test_submit_report_stored():
    with tempfile.TemporaryDirectory() as tmp:
        report_store, audit_logger, _, _ = _make_deps(Path(tmp))
        result = asyncio.run(_submit_debug_report(_valid_report(), report_store, audit_logger))
        data = json.loads(result[0].text)
        report_id = data["report_id"]
        loaded = report_store.load(report_id, DebugReport)
        assert loaded is not None
        assert loaded.ticket_id == "BUG-123"


def test_submit_report_audited():
    with tempfile.TemporaryDirectory() as tmp:
        report_store, audit_logger, event_store, _ = _make_deps(Path(tmp))
        asyncio.run(_submit_debug_report(_valid_report(), report_store, audit_logger))
        events = event_store.read_all()
        assert any(e["event_type"] == "report_submitted" for e in events)
