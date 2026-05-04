from __future__ import annotations

import json
from pathlib import Path


class MetabaseApiSpecLoader:
    """Loads the Metabase OpenAPI spec and validates allowed endpoints exist."""

    _ALLOWED = ["/api/session", "/api/dataset"]

    def __init__(self, spec_path: Path | None = None) -> None:
        if spec_path is None:
            spec_path = Path(__file__).resolve().parents[3] / "docs" / "metabase_api.json"
        self._spec: dict = json.loads(spec_path.read_text())

    @property
    def allowed_endpoints(self) -> list[str]:
        return list(self._ALLOWED)

    def has_endpoint(self, path: str) -> bool:
        return path in self._spec.get("paths", {}) and path in self._ALLOWED
