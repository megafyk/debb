from __future__ import annotations

import tempfile
from pathlib import Path

from evidence_gate.storage.raw_evidence_store import RawEvidenceStore


def test_store_and_load():
    with tempfile.TemporaryDirectory() as tmp:
        store = RawEvidenceStore(Path(tmp))
        hits = [{"ts": "2026-01-01T00:00:00Z", "msg": "hello"}]
        store.store("REQ-1", hits)
        loaded = store.load("REQ-1")
        assert loaded == hits


def test_load_missing():
    with tempfile.TemporaryDirectory() as tmp:
        store = RawEvidenceStore(Path(tmp))
        assert store.load("nonexistent") is None
