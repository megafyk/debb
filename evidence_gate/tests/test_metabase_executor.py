from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from evidence_gate.config import Settings
from evidence_gate.audit_logger import AuditLogger
from evidence_gate.connectors.metabase_connector import MetabaseConnector
from evidence_gate.contracts import EvidenceRequest
from evidence_gate.request_services.evidence_executor import execute_metabase_request
from evidence_gate.storage.sensitive_value_store import SensitiveValueStore
from evidence_gate.storage.evidence_request_store import EvidenceRequestStore
from evidence_gate.storage.json_store import JsonStore
from evidence_gate.storage.jsonl_event_store import JsonlEventStore
from evidence_gate.storage.masked_package_store import MaskedPackageStore
from evidence_gate.storage.raw_evidence_store import RawEvidenceStore


_PLAN_DICT = {
    "type": "metabase_query_plan",
    "evidence_session_id": "ESESS-1",
    "service": "login-service",
    "entity": "account",
    "query_intent": "Check account status",
    "facts_requested": ["account_exists", "account_status"],
    "params": [
        {"name": "phone_number", "value": "hashed_phone"},
        {"name": "tenant_salt", "value": "salt123"},
    ],
}


def _setup(tmp_path: Path):
    settings = Settings(metabase_url="", metabase_username="", metabase_password="")
    event_store = JsonlEventStore(tmp_path / "audit.jsonl")
    audit_logger = AuditLogger(event_store)
    sensitive_store = SensitiveValueStore(tmp_path)
    connector = MetabaseConnector(settings, sensitive_store, audit_logger)
    json_store = JsonStore(tmp_path, "requests")
    request_store = EvidenceRequestStore(json_store, audit_logger)
    raw_store = RawEvidenceStore(tmp_path)
    masked_store = MaskedPackageStore(tmp_path)
    return request_store, connector, raw_store, masked_store, audit_logger


def _make_bounded_request(request_store: EvidenceRequestStore) -> EvidenceRequest:
    req = EvidenceRequest(
        evidence_session_id="ESESS-1",
        request_type="metabase_query_plan",
        plan=_PLAN_DICT,
    )
    request_store.create(req)
    request_store.transition(req.evidence_request_id, "schema_checked")
    request_store.transition(req.evidence_request_id, "bounded")
    return request_store.get(req.evidence_request_id)


def test_execute_metabase_full_pipeline():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        request_store, connector, raw_store, masked_store, audit_logger = _setup(tmp_path)
        req = _make_bounded_request(request_store)

        pkg = asyncio.run(
            execute_metabase_request(
                req.evidence_request_id, request_store, connector,
                raw_store, masked_store, audit_logger, "ESESS-1",
            )
        )

        assert pkg.source_type == "metabase_query"
        final = request_store.get(req.evidence_request_id)
        assert final.state == "masked_package_ready"
        assert final.evidence_id == pkg.evidence_id


def test_execute_metabase_stores_raw():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        request_store, connector, raw_store, masked_store, audit_logger = _setup(tmp_path)
        req = _make_bounded_request(request_store)

        asyncio.run(
            execute_metabase_request(
                req.evidence_request_id, request_store, connector,
                raw_store, masked_store, audit_logger, "ESESS-1",
            )
        )

        raw = raw_store.load(req.evidence_request_id)
        assert raw is not None
        assert len(raw) == 1  # account fixture returns 1 row


def test_execute_metabase_stores_masked():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        request_store, connector, raw_store, masked_store, audit_logger = _setup(tmp_path)
        req = _make_bounded_request(request_store)

        pkg = asyncio.run(
            execute_metabase_request(
                req.evidence_request_id, request_store, connector,
                raw_store, masked_store, audit_logger, "ESESS-1",
            )
        )

        loaded = masked_store.load(pkg.evidence_id)
        assert loaded is not None
        assert loaded.source_type == "metabase_query"


def test_execute_metabase_wrong_state_raises():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        request_store, connector, raw_store, masked_store, audit_logger = _setup(tmp_path)

        req = EvidenceRequest(
            evidence_session_id="ESESS-1",
            request_type="metabase_query_plan",
            plan=_PLAN_DICT,
        )
        request_store.create(req)

        try:
            asyncio.run(
                execute_metabase_request(
                    req.evidence_request_id, request_store, connector,
                    raw_store, masked_store, audit_logger, "ESESS-1",
                )
            )
            assert False, "Should have raised ValueError"
        except ValueError as exc:
            assert "bounded" in str(exc).lower() or "created" in str(exc).lower()


def test_execute_metabase_transitions_to_failed_on_error():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        request_store, connector, raw_store, masked_store, audit_logger = _setup(tmp_path)

        req = EvidenceRequest(
            evidence_session_id="ESESS-1",
            request_type="metabase_query_plan",
            plan={"type": "metabase_query_plan", "bad_field": "nope"},
        )
        request_store.create(req)
        request_store.transition(req.evidence_request_id, "schema_checked")
        request_store.transition(req.evidence_request_id, "bounded")

        try:
            asyncio.run(
                execute_metabase_request(
                    req.evidence_request_id, request_store, connector,
                    raw_store, masked_store, audit_logger, "ESESS-1",
                )
            )
            assert False, "Should have raised"
        except Exception:
            pass

        final = request_store.get(req.evidence_request_id)
        assert final.state == "failed"
