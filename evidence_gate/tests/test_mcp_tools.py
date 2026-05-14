import asyncio
import json
import tempfile
from pathlib import Path

from evidence_gate.audit_logger import AuditLogger
from evidence_gate.connectors.jira_connector import JiraConnector
from evidence_gate.mcp_server.tools import (
    _get_sanitized_jira_ticket,
    _parse_ticket_id,
    _start_debugging_session,
)
from evidence_gate.storage.debug_report_evidence_store import DebugReportEvidenceStore
from evidence_gate.storage.evidence_session_store import EvidenceSessionStore
from evidence_gate.storage.sensitive_value_store import SensitiveValueStore
from evidence_gate.storage.jsonl_event_store import JsonlEventStore


def _make_deps(tmp_path: Path):
    session_store = EvidenceSessionStore(tmp_path)
    sensitive_store = SensitiveValueStore(tmp_path)
    audit_logger = AuditLogger(JsonlEventStore(tmp_path / "audit.jsonl"))
    jira_connector = JiraConnector()
    dr_store = DebugReportEvidenceStore(tmp_path)
    return session_store, sensitive_store, audit_logger, jira_connector, dr_store


def test_parse_ticket_id_from_url():
    assert _parse_ticket_id("https://company.atlassian.net/browse/BUG-123") == "BUG-123"


def test_parse_ticket_id_plain():
    assert _parse_ticket_id("BUG-123") == "BUG-123"


def test_parse_ticket_id_rejects_malformed():
    """ticket_id flows into the debug_reports/<TICKET_ID>_<DEBUG_SESSION_ID>/
    folder name — anything that doesn't match the Jira shape must be rejected
    upfront so we never persist evidence under a malformed directory."""
    import pytest as _pytest

    for bad in ("", "..", "../etc", "no-dash", "BUG-", "-123", "  BUG-123  ", "bug-123"):
        with _pytest.raises(ValueError):
            _parse_ticket_id(bad)


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


def test_start_debugging_session_generates_otel_trace_id_when_absent():
    """No trace_id passed → mint a 32-hex-char OTel trace id (W3C §3.2.2.3)."""
    with tempfile.TemporaryDirectory() as tmp:
        deps = _make_deps(Path(tmp))
        result = asyncio.run(
            _start_debugging_session("BUG-123", "", "", *deps)
        )
        data = json.loads(result[0].text)
        trace_id = data["trace_id"]
        assert len(trace_id) == 32
        assert all(c in "0123456789abcdef" for c in trace_id)
        # Not the OTel "invalid" all-zeros id.
        assert trace_id != "0" * 32


def test_start_debugging_session_preserves_caller_supplied_trace_id():
    """When a caller passes a trace_id, keep it verbatim so cross-system
    correlation (existing W3C traceparent) survives the boundary."""
    with tempfile.TemporaryDirectory() as tmp:
        deps = _make_deps(Path(tmp))
        supplied = "4bf92f3577b34da6a3ce929d0e0e4736"
        result = asyncio.run(
            _start_debugging_session("BUG-123", supplied, "", *deps)
        )
        data = json.loads(result[0].text)
        assert data["trace_id"] == supplied


def test_idempotent_reentry_backfills_empty_trace_id():
    """Legacy sessions saved before OTel auto-gen have trace_id=''. On
    idempotent re-entry we must mint one and persist it back — otherwise
    downstream evidence requests can't build the
    debug_reports/<TICKET_ID>_<DEBUG_SESSION_ID> folder (DEBUG_SESSION_ID =
    trace_id) and fail with a misleading 'connector failed' message."""
    from evidence_gate.contracts import EvidenceSession, SanitizedTicketContext

    with tempfile.TemporaryDirectory() as tmp:
        deps = _make_deps(Path(tmp))
        session_store = deps[0]

        # Simulate a pre-OTel session with empty trace_id but a cached
        # sanitized ticket (so the idempotent re-entry branch fires).
        legacy = EvidenceSession(
            ticket_id="BUG-123", trace_id="", idempotency_key="key-1",
            sanitized_ticket=SanitizedTicketContext(
                ticket_id="BUG-123", summary="s", issue_type="bug",
                priority="P2", status="open", description_sanitized="d",
            ),
        )
        session_store.save(legacy)

        result = asyncio.run(
            _start_debugging_session("BUG-123", "", "key-1", *deps)
        )
        data = json.loads(result[0].text)

        # Returned context has a fresh OTel trace id.
        trace_id = data["trace_id"]
        assert len(trace_id) == 32
        assert all(c in "0123456789abcdef" for c in trace_id)

        # And it was persisted — a second re-entry returns the same id.
        again = asyncio.run(
            _start_debugging_session("BUG-123", "", "key-1", *deps)
        )
        assert json.loads(again[0].text)["trace_id"] == trace_id


def test_start_debugging_session_persists_sanitized_ticket_under_jira_subdir():
    """The sanitized ticket must land in debug_reports/<folder>/jira/ so the
    debug report can cite it alongside the masked evidence files."""
    with tempfile.TemporaryDirectory() as tmp:
        deps = _make_deps(Path(tmp))
        result = asyncio.run(
            _start_debugging_session("BUG-123", "trace-1", "", *deps)
        )
        data = json.loads(result[0].text)

        out = Path(tmp) / "debug_reports" / f"BUG-123_{data['trace_id']}" / "jira" / "sanitized_ticket.json"
        assert out.exists()
        saved = json.loads(out.read_text())
        assert saved["ticket_id"] == "BUG-123"
        assert saved["summary"] == data["sanitized_ticket"]["summary"]


def test_idempotent_reentry_refreshes_jira_snapshot_after_trace_backfill():
    """Pre-OTel legacy sessions get a freshly-minted trace_id on re-entry; the
    Jira snapshot must be written to the new folder so the agent can find it."""
    from evidence_gate.contracts import EvidenceSession, SanitizedTicketContext

    with tempfile.TemporaryDirectory() as tmp:
        deps = _make_deps(Path(tmp))
        session_store = deps[0]
        legacy = EvidenceSession(
            ticket_id="BUG-123", trace_id="", idempotency_key="key-1",
            sanitized_ticket=SanitizedTicketContext(
                ticket_id="BUG-123", summary="legacy", issue_type="bug",
                priority="P2", status="open", description_sanitized="d",
            ),
        )
        session_store.save(legacy)

        result = asyncio.run(
            _start_debugging_session("BUG-123", "", "key-1", *deps)
        )
        data = json.loads(result[0].text)
        out = Path(tmp) / "debug_reports" / f"BUG-123_{data['trace_id']}" / "jira" / "sanitized_ticket.json"
        assert out.exists()


def test_get_sanitized_jira_ticket():
    with tempfile.TemporaryDirectory() as tmp:
        deps = _make_deps(Path(tmp))
        # First create a session
        result = asyncio.run(
            _start_debugging_session("BUG-123", "", "", *deps)
        )
        session_id = json.loads(result[0].text)["evidence_session_id"]

        # Then get the ticket
        session_store, sensitive_store, _audit, jira, _dr = deps
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

        session_store, sensitive_store, _audit, jira, _dr = deps
        second = asyncio.run(
            _get_sanitized_jira_ticket(session_id, session_store, sensitive_store, jira)
        )
        second_data = json.loads(second[0].text)
        # Both responses redact PII via the same ref scheme
        assert "SECURE_VALUE_REF_" in first_data["sanitized_ticket"]["description_sanitized"]
        assert "SECURE_VALUE_REF_" in second_data["description_sanitized"]


def test_get_sanitized_jira_ticket_missing_session():
    with tempfile.TemporaryDirectory() as tmp:
        deps = _make_deps(Path(tmp))
        session_store, sensitive_store, _audit, jira, _dr = deps
        result = asyncio.run(
            _get_sanitized_jira_ticket("nonexistent", session_store, sensitive_store, jira)
        )
        data = json.loads(result[0].text)
        assert "error" in data
