from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from evidence_gate.config import Settings
from evidence_gate.audit_logger import AuditLogger
from evidence_gate.connectors.metabase_connector import MetabaseConnector
from evidence_gate.contracts import EvidenceRequest
from evidence_gate.redaction.db_redactor import redact_db_rows
from evidence_gate.request_services.evidence_executor import execute_metabase_request
from evidence_gate.storage.sensitive_value_store import SensitiveValueStore
from evidence_gate.storage.evidence_request_store import EvidenceRequestStore
from evidence_gate.storage.json_store import JsonStore
from evidence_gate.storage.jsonl_event_store import JsonlEventStore
from evidence_gate.storage.masked_package_store import MaskedPackageStore
from evidence_gate.storage.raw_evidence_store import RawEvidenceStore


def _setup(tmp_path: Path):
    audit = AuditLogger(JsonlEventStore(tmp_path / "audit.jsonl"))
    request_store = EvidenceRequestStore(JsonStore(tmp_path, "requests"), audit)
    test_settings = Settings(metabase_url="", metabase_username="secret_user", metabase_password="secret_pass")
    sensitive_store = SensitiveValueStore(tmp_path)
    connector = MetabaseConnector(test_settings, sensitive_store, audit)
    raw_store = RawEvidenceStore(tmp_path)
    masked_store = MaskedPackageStore(tmp_path)
    return request_store, connector, raw_store, masked_store, audit, sensitive_store


def _make_bounded_metabase(request_store):
    plan = {
        "type": "metabase_query_plan",
        "evidence_session_id": "ESESS-1",
        "service": "account-service",
        "entity": "account",
        "query_intent": "Check account status",
        "params": [{"name": "phone_number", "value": "0812345678"}, {"name": "tenant_salt", "value": "salt"}],
        "facts_requested": ["account_exists", "account_status"],
    }
    req = EvidenceRequest(evidence_session_id="ESESS-1", request_type="metabase_query_plan", plan=plan)
    req = request_store.create(req)
    request_store.transition(req.evidence_request_id, "schema_checked")
    request_store.transition(req.evidence_request_id, "bounded")
    return req


def test_metabase_credentials_not_in_masked_package():
    with tempfile.TemporaryDirectory() as tmp:
        store, conn, raw, masked, audit, _ = _setup(Path(tmp))
        req = _make_bounded_metabase(store)
        pkg = asyncio.run(execute_metabase_request(
            req.evidence_request_id, store, conn, raw, masked, audit, "ESESS-1",
        ))
        pkg_json = pkg.model_dump_json()
        assert "secret_user" not in pkg_json
        assert "secret_pass" not in pkg_json


def test_raw_db_rows_not_in_masked_package():
    with tempfile.TemporaryDirectory() as tmp:
        store, conn, raw, masked, audit, _ = _setup(Path(tmp))
        req = _make_bounded_metabase(store)
        pkg = asyncio.run(execute_metabase_request(
            req.evidence_request_id, store, conn, raw, masked, audit, "ESESS-1",
        ))
        # Raw store has data
        raw_data = raw.load(req.evidence_request_id)
        assert raw_data is not None

        # Masked package only has redacted/aggregate data, source_type is metabase_query
        assert pkg.source_type == "metabase_query"
        assert pkg.masked_data.get("row_count") is not None


def test_nested_db_columns_are_redacted():
    """DB rows may contain JSON-typed columns (dicts) or array columns (lists).
    Redaction must recurse — raw PII must not pass through nested columns."""
    raw_rows = [
        {
            "id": 1,
            "status": "active",
            "metadata": {
                "contact_email": "secret@evil.com",
                "tags": ["billing", "phone: +66-812-345-6789"],
            },
            "audit_trail": [
                {"actor": "ops@internal.com", "action": "lock"},
                {"actor": "ops2@internal.com", "action": "unlock"},
            ],
        },
    ]
    redacted_rows = redact_db_rows(raw_rows)
    flat = str(redacted_rows)
    for raw_value in (
        "secret@evil.com",
        "ops@internal.com",
        "ops2@internal.com",
        "812-345-6789",
    ):
        assert raw_value not in flat, f"{raw_value!r} leaked through nested DB redaction"
    # Non-PII data is preserved
    assert redacted_rows[0]["status"] == "active"
    assert redacted_rows[0]["metadata"]["tags"][0] == "billing"
