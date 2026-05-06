"""Idempotency: same (ticket_id, idempotency_key) returns the same context."""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from evidence_gate.audit_logger import AuditLogger
from evidence_gate.connectors.jira_connector import JiraConnector
from evidence_gate.contracts import EvidenceSession
from evidence_gate.mcp_server.tools import _start_debugging_session
from evidence_gate.storage.evidence_session_store import EvidenceSessionStore
from evidence_gate.storage.sensitive_value_store import SensitiveValueStore
from evidence_gate.storage.jsonl_event_store import JsonlEventStore


def _make_deps(tmp_path: Path):
    session_store = EvidenceSessionStore(tmp_path)
    sensitive_store = SensitiveValueStore(tmp_path)
    audit_logger = AuditLogger(JsonlEventStore(tmp_path / "audit.jsonl"))
    jira = JiraConnector()
    return session_store, sensitive_store, audit_logger, jira


def test_idempotent_re_entry_returns_same_session_and_refs():
    """Calling start_debugging_session twice with the same key must return identical context."""
    with tempfile.TemporaryDirectory() as tmp:
        deps = _make_deps(Path(tmp))
        first = asyncio.run(_start_debugging_session("BUG-123", "trace-1", "key-1", *deps))
        second = asyncio.run(_start_debugging_session("BUG-123", "trace-1", "key-1", *deps))

        first_data = json.loads(first[0].text)
        second_data = json.loads(second[0].text)

        assert first_data["evidence_session_id"] == second_data["evidence_session_id"]
        # Sanitized text uses the same refs in both calls
        assert first_data["sanitized_ticket"] == second_data["sanitized_ticket"]
        # Sensitive refs metadata is identical
        assert first_data["sensitive_refs"] == second_data["sensitive_refs"]


def test_idempotent_re_entry_does_not_create_duplicate_refs():
    """Idempotent calls must not store new sensitive refs each time."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        deps = _make_deps(tmp_path)

        first = asyncio.run(_start_debugging_session("BUG-123", "", "key-1", *deps))
        session_id = json.loads(first[0].text)["evidence_session_id"]
        refs_file = tmp_path / "sensitive_values" / f"{session_id}.json"
        first_count = len(json.loads(refs_file.read_text()))

        asyncio.run(_start_debugging_session("BUG-123", "", "key-1", *deps))
        second_count = len(json.loads(refs_file.read_text()))

        assert first_count == second_count, "Idempotent re-entry created duplicate refs"


def test_different_idempotency_keys_create_distinct_sessions():
    """Two different idempotency keys for the same ticket must produce distinct sessions."""
    with tempfile.TemporaryDirectory() as tmp:
        deps = _make_deps(Path(tmp))
        first = asyncio.run(_start_debugging_session("BUG-123", "", "key-A", *deps))
        second = asyncio.run(_start_debugging_session("BUG-123", "", "key-B", *deps))

        first_id = json.loads(first[0].text)["evidence_session_id"]
        second_id = json.loads(second[0].text)["evidence_session_id"]
        assert first_id != second_id


def test_idempotency_finds_correct_session_when_multiple_exist():
    """find_idempotent must match by (ticket_id, idempotency_key), not by ticket_id alone."""
    with tempfile.TemporaryDirectory() as tmp:
        deps = _make_deps(Path(tmp))
        # Create two sessions for the same ticket with different keys
        a_first = asyncio.run(_start_debugging_session("BUG-123", "", "key-A", *deps))
        b_first = asyncio.run(_start_debugging_session("BUG-123", "", "key-B", *deps))

        # Re-entering with key-B must hit the B session, not the A session
        b_second = asyncio.run(_start_debugging_session("BUG-123", "", "key-B", *deps))

        b_first_id = json.loads(b_first[0].text)["evidence_session_id"]
        b_second_id = json.loads(b_second[0].text)["evidence_session_id"]
        a_first_id = json.loads(a_first[0].text)["evidence_session_id"]

        assert b_first_id == b_second_id
        assert b_second_id != a_first_id


def test_no_idempotency_key_always_creates_new_session():
    """Empty idempotency_key must never short-circuit to an existing session."""
    with tempfile.TemporaryDirectory() as tmp:
        deps = _make_deps(Path(tmp))
        first = asyncio.run(_start_debugging_session("BUG-123", "", "", *deps))
        second = asyncio.run(_start_debugging_session("BUG-123", "", "", *deps))
        assert (
            json.loads(first[0].text)["evidence_session_id"]
            != json.loads(second[0].text)["evidence_session_id"]
        )


def test_session_store_find_idempotent_requires_both_fields():
    with tempfile.TemporaryDirectory() as tmp:
        store = EvidenceSessionStore(Path(tmp))
        a = EvidenceSession(ticket_id="BUG-1", idempotency_key="K1")
        b = EvidenceSession(ticket_id="BUG-1", idempotency_key="K2")
        store.save(a)
        store.save(b)

        assert store.find_idempotent("BUG-1", "K1").evidence_session_id == a.evidence_session_id
        assert store.find_idempotent("BUG-1", "K2").evidence_session_id == b.evidence_session_id
        assert store.find_idempotent("BUG-1", "K3") is None
        # Empty key never matches
        assert store.find_idempotent("BUG-1", "") is None
