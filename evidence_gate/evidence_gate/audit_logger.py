from __future__ import annotations

from evidence_gate.contracts import AuditEvent
from evidence_gate.storage.jsonl_event_store import JsonlEventStore


class AuditLogger:
    def __init__(self, event_store: JsonlEventStore) -> None:
        self._store = event_store

    def log(self, session_id: str, event_type: str, details: dict | None = None) -> AuditEvent:
        event = AuditEvent(
            evidence_session_id=session_id,
            event_type=event_type,
            details=details or {},
        )
        self._store.append(event)
        return event
