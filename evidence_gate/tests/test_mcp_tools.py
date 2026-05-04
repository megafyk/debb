import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from evidence_gate.audit.audit_logger import AuditLogger
from evidence_gate.connectors.jira_connector import JiraConnector
from evidence_gate.mcp_server.tools import _parse_ticket_id, _start_debugging_session, _get_sanitized_jira_ticket
from evidence_gate.sessions.evidence_session_store import EvidenceSessionStore
from evidence_gate.sessions.sensitive_value_store import SensitiveValueStore
from evidence_gate.storage.jsonl_event_store import JsonlEventStore


def _make_deps(tmp_path: Path):
    session_store = EvidenceSessionStore(tmp_path)
    sensitive_store = SensitiveValueStore(tmp_path)
    audit_logger = AuditLogger(JsonlEventStore(tmp_path / "audit.jsonl"))
    jira_connector = JiraConnector()
    return session_store, sensitive_store, audit_logger, jira_connector


def test_parse_ticket_id_from_url():
    assert _parse_ticket_id("https://company.atlassian.net/browse/BUG-123") == "BUG-123"


def test_parse_ticket_id_plain():
    assert _parse_ticket_id("BUG-123") == "BUG-123"


def test_start_debugging_session():
    with tempfile.TemporaryDirectory() as tmp:
        deps = _make_deps(Path(tmp))
        result = asyncio.run(
            _start_debugging_session("BUG-123", "trace-1", "", *deps)
        )
        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["ticket_id"] == "BUG-123"
        assert data["evidence_session_id"].startswith("ESESS-")
        assert data["sanitized_ticket"]["summary"] == "Login fails for users with phone numbers missing leading zero"
        # Verify redaction happened
        assert "somchai@example.com" not in data["sanitized_ticket"]["description_sanitized"]


def test_get_sanitized_jira_ticket():
    with tempfile.TemporaryDirectory() as tmp:
        deps = _make_deps(Path(tmp))
        # First create a session
        result = asyncio.run(
            _start_debugging_session("BUG-123", "", "", *deps)
        )
        session_id = json.loads(result[0].text)["evidence_session_id"]

        # Then get the ticket
        session_store = deps[0]
        jira = deps[3]
        result2 = asyncio.run(
            _get_sanitized_jira_ticket(session_id, session_store, jira)
        )
        data = json.loads(result2[0].text)
        assert data["ticket_id"] == "BUG-123"


def test_get_sanitized_jira_ticket_missing_session():
    with tempfile.TemporaryDirectory() as tmp:
        deps = _make_deps(Path(tmp))
        result = asyncio.run(
            _get_sanitized_jira_ticket("nonexistent", deps[0], deps[3])
        )
        data = json.loads(result[0].text)
        assert "error" in data
