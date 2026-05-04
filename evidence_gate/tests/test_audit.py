import tempfile
from pathlib import Path

from evidence_gate.audit.audit_logger import AuditLogger
from evidence_gate.storage.jsonl_event_store import JsonlEventStore


def test_audit_logger():
    with tempfile.TemporaryDirectory() as tmp:
        store = JsonlEventStore(Path(tmp) / "audit.jsonl")
        logger = AuditLogger(store)

        event = logger.log("ESESS-1", "session_created", {"ticket_id": "BUG-1"})
        assert event.audit_id.startswith("AUD-")
        assert event.event_type == "session_created"

        events = store.read_all()
        assert len(events) == 1
        assert events[0]["details"]["ticket_id"] == "BUG-1"
