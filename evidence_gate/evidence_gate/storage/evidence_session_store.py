from __future__ import annotations

import json
from pathlib import Path

from evidence_gate.contracts import EvidenceSession


class EvidenceSessionStore:
    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "sessions"
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, session: EvidenceSession) -> None:
        path = self._dir / f"{session.evidence_session_id}.json"
        path.write_text(session.model_dump_json(indent=2))

    def get(self, session_id: str) -> EvidenceSession | None:
        path = self._dir / f"{session_id}.json"
        if not path.exists():
            return None
        return EvidenceSession.model_validate_json(path.read_text())

    def find_idempotent(self, ticket_id: str, idempotency_key: str) -> EvidenceSession | None:
        if not idempotency_key:
            return None
        for path in self._dir.glob("*.json"):
            data = json.loads(path.read_text())
            if data.get("ticket_id") == ticket_id and data.get("idempotency_key") == idempotency_key:
                return EvidenceSession.model_validate(data)
        return None
