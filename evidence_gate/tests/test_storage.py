import tempfile
from pathlib import Path

from evidence_gate.contracts.audit import AuditEvent
from evidence_gate.contracts.evidence_request import EvidenceRequest
from evidence_gate.storage.json_store import JsonStore
from evidence_gate.storage.jsonl_event_store import JsonlEventStore


def test_json_store_save_and_load():
    with tempfile.TemporaryDirectory() as tmp:
        store = JsonStore(Path(tmp), "requests")
        req = EvidenceRequest(evidence_session_id="ESESS-1", request_type="quickwit_query_plan")
        store.save(req.evidence_request_id, req)

        loaded = store.load(req.evidence_request_id, EvidenceRequest)
        assert loaded is not None
        assert loaded.evidence_session_id == "ESESS-1"


def test_json_store_load_missing():
    with tempfile.TemporaryDirectory() as tmp:
        store = JsonStore(Path(tmp), "requests")
        assert store.load("nonexistent", EvidenceRequest) is None


def test_json_store_list_keys():
    with tempfile.TemporaryDirectory() as tmp:
        store = JsonStore(Path(tmp), "requests")
        req1 = EvidenceRequest(evidence_session_id="ESESS-1", request_type="quickwit_query_plan")
        req2 = EvidenceRequest(evidence_session_id="ESESS-2", request_type="metabase_query_plan")
        store.save("req1", req1)
        store.save("req2", req2)

        keys = store.list_keys()
        assert set(keys) == {"req1", "req2"}


def test_jsonl_event_store():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        store = JsonlEventStore(path)

        e1 = AuditEvent(evidence_session_id="ESESS-1", event_type="session_created")
        e2 = AuditEvent(evidence_session_id="ESESS-1", event_type="ticket_fetched")
        store.append(e1)
        store.append(e2)

        events = store.read_all()
        assert len(events) == 2
        assert events[0]["event_type"] == "session_created"
        assert events[1]["event_type"] == "ticket_fetched"


def test_jsonl_event_store_empty():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        store = JsonlEventStore(path)
        assert store.read_all() == []
