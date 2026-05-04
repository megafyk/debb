from __future__ import annotations

import json
from pathlib import Path


class RawEvidenceStore:
    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "raw_evidence"
        self._dir.mkdir(parents=True, exist_ok=True)

    def store(self, request_id: str, raw_hits: list[dict]) -> None:
        path = self._dir / f"{request_id}.json"
        path.write_text(json.dumps(raw_hits, indent=2, default=str))

    def load(self, request_id: str) -> list[dict] | None:
        path = self._dir / f"{request_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text())
