from __future__ import annotations

from datetime import UTC, datetime

from evidence_gate.audit.audit_logger import AuditLogger
from evidence_gate.contracts.evidence_request import EvidenceRequest
from evidence_gate.storage.json_store import JsonStore


# Valid state transitions
_TRANSITIONS: dict[str, set[str]] = {
    "created": {"schema_checked", "rejected"},
    "schema_checked": {"rejected", "bounded"},
    "bounded": {"connector_running"},
    "connector_running": {"raw_evidence_stored", "failed"},
    "raw_evidence_stored": {"redaction_running"},
    "redaction_running": {"masked_package_ready", "failed"},
}

_TERMINAL = {"rejected", "masked_package_ready", "failed", "expired"}


class EvidenceRequestStore:
    def __init__(self, store: JsonStore, audit_logger: AuditLogger) -> None:
        self._store = store
        self._audit = audit_logger

    def create(self, request: EvidenceRequest) -> EvidenceRequest:
        self._store.save(request.evidence_request_id, request)
        self._audit.log(
            request.evidence_session_id,
            "request_created",
            {"request_id": request.evidence_request_id, "type": request.request_type},
        )
        return request

    def get(self, request_id: str) -> EvidenceRequest | None:
        return self._store.load(request_id, EvidenceRequest)

    def transition(self, request_id: str, new_state: str, details: dict | None = None) -> EvidenceRequest:
        request = self.get(request_id)
        if request is None:
            raise ValueError(f"Request not found: {request_id}")

        current = request.state
        if current in _TERMINAL:
            raise ValueError(f"Cannot transition from terminal state: {current}")

        allowed = _TRANSITIONS.get(current, set())
        if new_state not in allowed:
            raise ValueError(f"Invalid transition: {current} -> {new_state}")

        request.state = new_state
        request.updated_at = datetime.now(UTC)

        if details:
            if "rejection_reason" in details:
                request.rejection_reason = details["rejection_reason"]
            if "narrowing_applied" in details:
                request.narrowing_applied = details["narrowing_applied"]
            if "evidence_id" in details:
                request.evidence_id = details["evidence_id"]

        audit_event = self._audit.log(
            request.evidence_session_id,
            "request_state_changed",
            {"request_id": request_id, "from": current, "to": new_state, **(details or {})},
        )
        request.audit_refs.append(audit_event.audit_id)

        self._store.save(request_id, request)
        return request
