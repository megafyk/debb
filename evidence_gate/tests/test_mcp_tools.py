import asyncio
import json
import tempfile
from pathlib import Path

from evidence_gate.audit_logger import AuditLogger
from evidence_gate.connectors.jira_connector import JiraConnector
from evidence_gate.mcp_server.tools import (
    _get_sanitized_jira_ticket,
    _list_evidence_templates,
    _parse_ticket_id,
    _start_debugging_session,
)
from evidence_gate.storage.evidence_session_store import EvidenceSessionStore
from evidence_gate.storage.sensitive_value_store import SensitiveValueStore
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
        session_store, sensitive_store, _audit, jira = deps
        result2 = asyncio.run(
            _get_sanitized_jira_ticket(session_id, session_store, sensitive_store, jira)
        )
        data = json.loads(result2[0].text)
        assert data["ticket_id"] == "BUG-123"
        # Raw PII never appears in the response
        flat = result2[0].text
        assert "somchai@example.com" not in flat
        assert "support@company.com" not in flat
        assert "+66812345678" not in flat
        # Refs follow the SECURE_VALUE_REF format established by start_debugging_session,
        # not the generic [REDACTED_*] placeholder. This keeps the agent's view consistent
        # so it can use matches_sensitive_ref filters.
        assert "SECURE_VALUE_REF_email_" in flat
        assert "SECURE_VALUE_REF_phone_number_" in flat


def test_get_sanitized_jira_ticket_consistent_with_start():
    """The ref format from get_sanitized_jira_ticket must match start_debugging_session."""
    with tempfile.TemporaryDirectory() as tmp:
        deps = _make_deps(Path(tmp))
        first = asyncio.run(_start_debugging_session("BUG-123", "", "", *deps))
        first_data = json.loads(first[0].text)
        session_id = first_data["evidence_session_id"]

        session_store, sensitive_store, _audit, jira = deps
        second = asyncio.run(
            _get_sanitized_jira_ticket(session_id, session_store, sensitive_store, jira)
        )
        second_data = json.loads(second[0].text)
        # Both responses redact PII via the same ref scheme
        assert "SECURE_VALUE_REF_" in first_data["sanitized_ticket"]["description_sanitized"]
        assert "SECURE_VALUE_REF_" in second_data["description_sanitized"]


def test_list_evidence_templates():
    result = asyncio.run(_list_evidence_templates())
    data = json.loads(result[0].text)
    assert "templates" in data
    template_ids = {t["template_id"] for t in data["templates"]}
    assert "account_status_by_phone_hash" in template_ids
    assert "login_attempt_counts" in template_ids
    # No raw secrets in the listing
    payload_text = result[0].text
    assert "password" not in payload_text.lower()
    assert "session" not in payload_text.lower()


def test_get_sanitized_jira_ticket_missing_session():
    with tempfile.TemporaryDirectory() as tmp:
        deps = _make_deps(Path(tmp))
        session_store, sensitive_store, _audit, jira = deps
        result = asyncio.run(
            _get_sanitized_jira_ticket("nonexistent", session_store, sensitive_store, jira)
        )
        data = json.loads(result[0].text)
        assert "error" in data
