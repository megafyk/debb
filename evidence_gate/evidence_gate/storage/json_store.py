from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


class JsonStore:
    def __init__(self, data_dir: Path, subdirectory: str) -> None:
        self._dir = data_dir / subdirectory
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, key: str, model: BaseModel) -> Path:
        path = self._dir / f"{key}.json"
        path.write_text(model.model_dump_json(indent=2))
        return path

    def load(self, key: str, model_class: type[BaseModel]) -> BaseModel | None:
        path = self._dir / f"{key}.json"
        if not path.exists():
            return None
        return model_class.model_validate_json(path.read_text())

    def list_keys(self) -> list[str]:
        return [p.stem for p in self._dir.glob("*.json")]
