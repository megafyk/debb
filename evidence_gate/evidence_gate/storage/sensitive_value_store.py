from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4


class SensitiveValueStore:
    """Stores raw sensitive values mapped to secure refs. Never exposes values to agents."""

    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "sensitive_values"
        self._dir.mkdir(parents=True, exist_ok=True)

    def store(self, session_id: str, field_type: str, raw_value: str) -> str:
        value_ref = f"SECURE_VALUE_REF_{field_type}_{uuid4().hex[:6]}"
        path = self._dir / f"{session_id}.json"
        data: dict = {}
        if path.exists():
            data = json.loads(path.read_text())
        data[value_ref] = {"field_type": field_type, "raw_value": raw_value}
        path.write_text(json.dumps(data, indent=2))
        return value_ref

    def resolve(self, session_id: str, value_ref: str) -> str | None:
        path = self._dir / f"{session_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        entry = data.get(value_ref)
        return entry["raw_value"] if entry else None
