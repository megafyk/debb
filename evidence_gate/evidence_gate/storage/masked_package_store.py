from __future__ import annotations

from pathlib import Path

from evidence_gate.contracts.masked_evidence_package import MaskedEvidencePackage


class MaskedPackageStore:
    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "masked_packages"
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, package: MaskedEvidencePackage) -> None:
        path = self._dir / f"{package.evidence_id}.json"
        path.write_text(package.model_dump_json(indent=2))

    def load(self, evidence_id: str) -> MaskedEvidencePackage | None:
        path = self._dir / f"{evidence_id}.json"
        if not path.exists():
            return None
        return MaskedEvidencePackage.model_validate_json(path.read_text())
