from __future__ import annotations

import tempfile
from pathlib import Path

from evidence_gate.contracts import MaskedEvidencePackage
from evidence_gate.storage.masked_package_store import MaskedPackageStore


def test_save_and_load():
    with tempfile.TemporaryDirectory() as tmp:
        store = MaskedPackageStore(Path(tmp))
        pkg = MaskedEvidencePackage(
            evidence_session_id="ESESS-1",
            evidence_request_id="EREQ-abc",
            source_type="quickwit_logs",
            masked_data={"hits": [{"a": "1"}], "total_hits": 1, "fields": ["a"]},
            audit_ref="AUD-xyz",
        )
        store.save(pkg)
        loaded = store.load(pkg.evidence_id)
        assert loaded is not None
        assert loaded.evidence_id == pkg.evidence_id
        assert loaded.source_type == "quickwit_logs"
        assert loaded.masked_data == pkg.masked_data


def test_load_missing():
    with tempfile.TemporaryDirectory() as tmp:
        store = MaskedPackageStore(Path(tmp))
        assert store.load("nonexistent") is None
