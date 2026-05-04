from __future__ import annotations

from pathlib import Path

from evidence_gate.connectors.metabase_api_spec_loader import MetabaseApiSpecLoader


def test_allowed_endpoints():
    loader = MetabaseApiSpecLoader()
    assert "/api/session" in loader.allowed_endpoints
    assert "/api/dataset" in loader.allowed_endpoints


def test_has_endpoint_true():
    loader = MetabaseApiSpecLoader()
    assert loader.has_endpoint("/api/session") is True
    assert loader.has_endpoint("/api/dataset") is True


def test_has_endpoint_false_for_unlisted():
    loader = MetabaseApiSpecLoader()
    assert loader.has_endpoint("/api/card") is False


def test_has_endpoint_false_for_nonexistent():
    loader = MetabaseApiSpecLoader()
    assert loader.has_endpoint("/api/totally_fake") is False
