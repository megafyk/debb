import asyncio
import json
import tempfile
from pathlib import Path

from evidence_gate.audit.audit_logger import AuditLogger
from evidence_gate.connectors.jira_connector import JiraConnector
from evidence_gate.mcp_server.tools import _start_debugging_session
from evidence_gate.sessions.evidence_session_store import EvidenceSessionStore
from evidence_gate.sessions.sensitive_value_store import SensitiveValueStore
from evidence_gate.storage.jsonl_event_store import JsonlEventStore

# Raw values that must never appear in agent output
FORBIDDEN_STRINGS = [
    "somchai@example.com",
    "+66812345678",
    "support@company.com",
]


def test_no_raw_pii_in_session_context():
    """The start_debugging_session response must not contain raw PII."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        session_store = EvidenceSessionStore(tmp_path)
        sensitive_store = SensitiveValueStore(tmp_path)
        audit_logger = AuditLogger(JsonlEventStore(tmp_path / "audit.jsonl"))
        jira = JiraConnector()

        result = asyncio.run(
            _start_debugging_session("BUG-123", "", "", session_store, sensitive_store, audit_logger, jira)
        )

        response_text = result[0].text
        for forbidden in FORBIDDEN_STRINGS:
            assert forbidden not in response_text, f"Raw PII leaked: {forbidden}"


def test_no_raw_pii_in_sanitized_ticket():
    """The sanitized ticket must not contain raw PII from fixture."""
    jira = JiraConnector()
    ticket = jira.fetch_and_sanitize("BUG-123")
    ticket_json = ticket.model_dump_json()

    for forbidden in FORBIDDEN_STRINGS:
        assert forbidden not in ticket_json, f"Raw PII in sanitized ticket: {forbidden}"
