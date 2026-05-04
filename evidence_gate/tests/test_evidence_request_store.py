import tempfile
from pathlib import Path

import pytest

from evidence_gate.audit.audit_logger import AuditLogger
from evidence_gate.contracts.evidence_request import EvidenceRequest
from evidence_gate.storage.evidence_request_store import EvidenceRequestStore
from evidence_gate.storage.json_store import JsonStore
from evidence_gate.storage.jsonl_event_store import JsonlEventStore


def _make_store(tmp_path: Path):
    json_store = JsonStore(tmp_path, "requests")
    audit_logger = AuditLogger(JsonlEventStore(tmp_path / "audit.jsonl"))
    return EvidenceRequestStore(json_store, audit_logger)


def test_create_and_get():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(Path(tmp))
        req = EvidenceRequest(evidence_session_id="ESESS-1", request_type="quickwit_query_plan")
        created = store.create(req)
        assert created.state == "created"

        loaded = store.get(created.evidence_request_id)
        assert loaded is not None
        assert loaded.evidence_session_id == "ESESS-1"


def test_valid_transition():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(Path(tmp))
        req = EvidenceRequest(evidence_session_id="ESESS-1", request_type="quickwit_query_plan")
        store.create(req)

        updated = store.transition(req.evidence_request_id, "schema_checked")
        assert updated.state == "schema_checked"

        updated = store.transition(req.evidence_request_id, "bounded")
        assert updated.state == "bounded"


def test_invalid_transition_raises():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(Path(tmp))
        req = EvidenceRequest(evidence_session_id="ESESS-1", request_type="quickwit_query_plan")
        store.create(req)

        with pytest.raises(ValueError, match="Invalid transition"):
            store.transition(req.evidence_request_id, "bounded")  # skip schema_checked


def test_terminal_state_blocks_transition():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(Path(tmp))
        req = EvidenceRequest(evidence_session_id="ESESS-1", request_type="quickwit_query_plan")
        store.create(req)
        store.transition(req.evidence_request_id, "rejected", {"rejection_reason": "test"})

        with pytest.raises(ValueError, match="terminal state"):
            store.transition(req.evidence_request_id, "schema_checked")


def test_transition_appends_audit_ref():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(Path(tmp))
        req = EvidenceRequest(evidence_session_id="ESESS-1", request_type="quickwit_query_plan")
        store.create(req)
        updated = store.transition(req.evidence_request_id, "schema_checked")
        assert len(updated.audit_refs) >= 1
        assert updated.audit_refs[-1].startswith("AUD-")


def test_rejection_stores_reason():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(Path(tmp))
        req = EvidenceRequest(evidence_session_id="ESESS-1", request_type="quickwit_query_plan")
        store.create(req)
        updated = store.transition(req.evidence_request_id, "rejected", {"rejection_reason": "unsafe SQL"})
        assert updated.rejection_reason == "unsafe SQL"
