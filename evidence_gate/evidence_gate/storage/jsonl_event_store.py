from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


class JsonlEventStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: BaseModel) -> None:
        with open(self._path, "a") as f:
            f.write(event.model_dump_json() + "\n")

    def read_all(self) -> list[dict]:
        if not self._path.exists():
            return []
        events = []
        for line in self._path.read_text().splitlines():
            if line.strip():
                events.append(json.loads(line))
        return events
