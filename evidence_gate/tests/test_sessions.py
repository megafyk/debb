import tempfile
from pathlib import Path

from evidence_gate.contracts import EvidenceSession
from evidence_gate.storage.evidence_session_store import EvidenceSessionStore
from evidence_gate.storage.sensitive_value_store import SensitiveValueStore


def test_session_store_save_and_get():
    with tempfile.TemporaryDirectory() as tmp:
        store = EvidenceSessionStore(Path(tmp))
        session = EvidenceSession(ticket_id="BUG-1", trace_id="trace-abc")
        store.save(session)

        loaded = store.get(session.evidence_session_id)
        assert loaded is not None
        assert loaded.ticket_id == "BUG-1"
        assert loaded.trace_id == "trace-abc"


def test_session_store_get_missing():
    with tempfile.TemporaryDirectory() as tmp:
        store = EvidenceSessionStore(Path(tmp))
        assert store.get("nonexistent") is None


def test_session_store_find_by_ticket():
    with tempfile.TemporaryDirectory() as tmp:
        store = EvidenceSessionStore(Path(tmp))
        session = EvidenceSession(ticket_id="BUG-42")
        store.save(session)

        found = store.find_by_ticket("BUG-42")
        assert found is not None
        assert found.evidence_session_id == session.evidence_session_id


def test_sensitive_value_store():
    with tempfile.TemporaryDirectory() as tmp:
        store = SensitiveValueStore(Path(tmp))
        ref = store.store("ESESS-1", "phone_number", "+66812345678")

        assert ref.startswith("SECURE_VALUE_REF_phone_number_")
        resolved = store.resolve("ESESS-1", ref)
        assert resolved == "+66812345678"


def test_sensitive_value_store_missing():
    with tempfile.TemporaryDirectory() as tmp:
        store = SensitiveValueStore(Path(tmp))
        assert store.resolve("ESESS-1", "nonexistent") is None
