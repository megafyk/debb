from __future__ import annotations

import tempfile
from pathlib import Path

from evidence_gate.connectors.metabase_param_resolver import resolve_params
from evidence_gate.connectors.metabase_template_registry import DbTemplate
from evidence_gate.sessions.sensitive_value_store import SensitiveValueStore


def _make_template() -> DbTemplate:
    return DbTemplate(
        template_id="test_tmpl",
        entity="account",
        description="test",
        sql="SELECT 1 WHERE x = :foo AND y = :bar",
        param_names=["foo", "bar"],
    )


def test_resolve_plain_values():
    tmpl = _make_template()
    params = [
        {"name": "foo", "value": "hello"},
        {"name": "bar", "value": "world"},
    ]
    with tempfile.TemporaryDirectory() as tmp:
        store = SensitiveValueStore(Path(tmp))
        result = resolve_params(tmpl, params, "ESESS-1", store)
    assert result == {"foo": "hello", "bar": "world"}


def test_resolve_secure_ref():
    tmpl = _make_template()
    with tempfile.TemporaryDirectory() as tmp:
        store = SensitiveValueStore(Path(tmp))
        ref = store.store("ESESS-1", "phone", "+1234567890")
        params = [
            {"name": "foo", "value_ref": ref},
            {"name": "bar", "value": "plain"},
        ]
        result = resolve_params(tmpl, params, "ESESS-1", store)
    assert result is not None
    assert result["foo"] == "+1234567890"
    assert result["bar"] == "plain"


def test_resolve_missing_param_returns_none():
    tmpl = _make_template()
    params = [{"name": "foo", "value": "hello"}]  # missing "bar"
    with tempfile.TemporaryDirectory() as tmp:
        store = SensitiveValueStore(Path(tmp))
        result = resolve_params(tmpl, params, "ESESS-1", store)
    assert result is None


def test_resolve_bad_ref_returns_none():
    tmpl = _make_template()
    params = [
        {"name": "foo", "value_ref": "SECURE_VALUE_REF_nonexistent"},
        {"name": "bar", "value": "ok"},
    ]
    with tempfile.TemporaryDirectory() as tmp:
        store = SensitiveValueStore(Path(tmp))
        result = resolve_params(tmpl, params, "ESESS-1", store)
    assert result is None


def test_resolve_connector_secret():
    tmpl = _make_template()
    params = [
        {"name": "foo", "source": "connector_secret"},
        {"name": "bar", "value": "plain"},
    ]
    with tempfile.TemporaryDirectory() as tmp:
        store = SensitiveValueStore(Path(tmp))
        result = resolve_params(tmpl, params, "ESESS-1", store)
    assert result == {"foo": "__CONNECTOR_SECRET__", "bar": "plain"}


def test_resolve_no_value_source_returns_none():
    tmpl = _make_template()
    params = [
        {"name": "foo"},  # no value, no value_ref, no source
        {"name": "bar", "value": "ok"},
    ]
    with tempfile.TemporaryDirectory() as tmp:
        store = SensitiveValueStore(Path(tmp))
        result = resolve_params(tmpl, params, "ESESS-1", store)
    assert result is None
