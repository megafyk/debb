"""Boundary tests: credentials and raw Jira data must never leak to agent-visible output."""

import asyncio
import json
import tempfile
from pathlib import Path

import httpx
import respx

from evidence_gate.config import Settings
from evidence_gate.audit_logger import AuditLogger
from evidence_gate.connectors.jira_connector import JiraConnector
from evidence_gate.mcp_server.tools import _start_debugging_session
from evidence_gate.storage.evidence_session_store import EvidenceSessionStore
from evidence_gate.storage.sensitive_value_store import SensitiveValueStore
from evidence_gate.storage.jsonl_event_store import JsonlEventStore


FORBIDDEN_CREDENTIAL_STRINGS = [
    "secret-api-token",
    "bot@internal.com",
    "Basic ",  # Auth header value
]

FORBIDDEN_PII = [
    "victim@example.com",
    "+66999888777",
]

_JIRA_RESPONSE = {
    "key": "SEC-1",
    "fields": {
        "summary": "Security boundary test ticket",
        "issuetype": {"name": "Bug"},
        "priority": {"name": "High"},
        "status": {"name": "Open"},
        "labels": [],
        "components": [],
        "description": "Customer victim@example.com called from +66999888777",
        "comment": {"comments": []},
        "created": "2026-05-01T00:00:00.000+0000",
        "updated": "2026-05-01T00:00:00.000+0000",
        "issuelinks": [],
        "subtasks": [],
    },
}


@respx.mock
def test_no_credentials_in_session_response():
    """Jira credentials must never appear in agent-visible MCP response."""
    settings = Settings(
        jira_base_url="https://test.atlassian.net",
        jira_username="bot@internal.com",
        jira_password="secret-api-token",
    )

    respx.get("https://test.atlassian.net/rest/api/2/issue/SEC-1").mock(
        return_value=httpx.Response(200, json=_JIRA_RESPONSE)
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        session_store = EvidenceSessionStore(tmp_path)
        sensitive_store = SensitiveValueStore(tmp_path)
        audit_logger = AuditLogger(JsonlEventStore(tmp_path / "audit.jsonl"))
        jira = JiraConnector(settings)

        result = asyncio.run(
            _start_debugging_session("SEC-1", "", "", session_store, sensitive_store, audit_logger, jira)
        )

    response_text = result[0].text
    for forbidden in FORBIDDEN_CREDENTIAL_STRINGS:
        assert forbidden not in response_text, f"Credential leaked in response: {forbidden}"


@respx.mock
def test_no_raw_pii_in_session_response():
    """Raw PII from Jira must be extracted/redacted before reaching the agent."""
    settings = Settings(
        jira_base_url="https://test.atlassian.net",
        jira_username="bot@internal.com",
        jira_password="secret-api-token",
    )

    respx.get("https://test.atlassian.net/rest/api/2/issue/SEC-1").mock(
        return_value=httpx.Response(200, json=_JIRA_RESPONSE)
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        session_store = EvidenceSessionStore(tmp_path)
        sensitive_store = SensitiveValueStore(tmp_path)
        audit_logger = AuditLogger(JsonlEventStore(tmp_path / "audit.jsonl"))
        jira = JiraConnector(settings)

        result = asyncio.run(
            _start_debugging_session("SEC-1", "", "", session_store, sensitive_store, audit_logger, jira)
        )

    response_text = result[0].text
    for forbidden in FORBIDDEN_PII:
        assert forbidden not in response_text, f"Raw PII leaked: {forbidden}"

    # Verify sensitive refs are present
    data = json.loads(response_text)
    assert len(data["sensitive_refs"]) > 0


@respx.mock
def test_no_credentials_in_audit_log():
    """Audit events must not contain Jira credentials."""
    settings = Settings(
        jira_base_url="https://test.atlassian.net",
        jira_username="bot@internal.com",
        jira_password="secret-api-token",
    )

    respx.get("https://test.atlassian.net/rest/api/2/issue/SEC-1").mock(
        return_value=httpx.Response(200, json=_JIRA_RESPONSE)
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        audit_path = tmp_path / "audit" / "events.jsonl"
        session_store = EvidenceSessionStore(tmp_path)
        sensitive_store = SensitiveValueStore(tmp_path)
        event_store = JsonlEventStore(audit_path)
        audit_logger = AuditLogger(event_store)
        jira = JiraConnector(settings)

        asyncio.run(
            _start_debugging_session("SEC-1", "", "", session_store, sensitive_store, audit_logger, jira)
        )

        audit_text = audit_path.read_text()
        for forbidden in FORBIDDEN_CREDENTIAL_STRINGS:
            assert forbidden not in audit_text, f"Credential leaked in audit: {forbidden}"
