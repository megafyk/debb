from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from evidence_gate.config import Settings
from evidence_gate.audit_logger import AuditLogger
from evidence_gate.connectors.quickwit_connector import QuickwitConnector
from evidence_gate.contracts import EvidenceRequest
from evidence_gate.request_services.evidence_executor import execute_quickwit_request
from evidence_gate.storage.sensitive_value_store import SensitiveValueStore
from evidence_gate.storage.evidence_request_store import EvidenceRequestStore
from evidence_gate.storage.json_store import JsonStore
from evidence_gate.storage.jsonl_event_store import JsonlEventStore
from evidence_gate.storage.masked_package_store import MaskedPackageStore
from evidence_gate.storage.raw_evidence_store import RawEvidenceStore

_PLAN_DICT = {
    "type": "quickwit_query_plan",
    "evidence_session_id": "ESESS-1",
    "service": "login-service",
    "datasource_uid": "login-service-prod",
    "from": "2026-01-01T00:00:00+00:00",
    "to": "2026-01-01T02:00:00+00:00",
    "query_intent": "Find login failures",
    "filters": [{"field": "error_code", "op": "=", "value": "ACCOUNT_LOOKUP_FAILED"}],
    "fields_requested": ["timestamp", "error_code"],
    "max_hits": 100,
}


def _setup(tmp_path: Path):
    settings = Settings(quickwit_url="", quickwit_username="", quickwit_password="")
    event_store = JsonlEventStore(tmp_path / "audit.jsonl")
    audit_logger = AuditLogger(event_store)
    sensitive_store = SensitiveValueStore(tmp_path)
    connector = QuickwitConnector(settings, sensitive_store, audit_logger)
    json_store = JsonStore(tmp_path, "requests")
    request_store = EvidenceRequestStore(json_store, audit_logger)
    raw_store = RawEvidenceStore(tmp_path)
    masked_store = MaskedPackageStore(tmp_path)
    return request_store, connector, raw_store, masked_store, audit_logger


def _make_bounded_request(request_store: EvidenceRequestStore) -> EvidenceRequest:
    req = EvidenceRequest(
        evidence_session_id="ESESS-1",
        request_type="quickwit_query_plan",
        plan=_PLAN_DICT,
    )
    request_store.create(req)
    request_store.transition(req.evidence_request_id, "schema_checked")
    request_store.transition(req.evidence_request_id, "bounded")
    return request_store.get(req.evidence_request_id)


def test_execute_full_pipeline():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        request_store, connector, raw_store, masked_store, audit_logger = _setup(tmp_path)
        req = _make_bounded_request(request_store)

        pkg = asyncio.run(
            execute_quickwit_request(
                req.evidence_request_id, request_store, connector,
                raw_store, masked_store, audit_logger, "ESESS-1",
            )
        )

        assert pkg.source_type == "quickwit_logs"
        final = request_store.get(req.evidence_request_id)
        assert final.state == "masked_package_ready"
        assert final.evidence_id == pkg.evidence_id


def test_execute_stores_raw_evidence():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        request_store, connector, raw_store, masked_store, audit_logger = _setup(tmp_path)
        req = _make_bounded_request(request_store)

        asyncio.run(
            execute_quickwit_request(
                req.evidence_request_id, request_store, connector,
                raw_store, masked_store, audit_logger, "ESESS-1",
            )
        )

        raw = raw_store.load(req.evidence_request_id)
        assert raw is not None
        assert len(raw) == 3  # fixture returns 3 hits


def test_execute_stores_masked_package():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        request_store, connector, raw_store, masked_store, audit_logger = _setup(tmp_path)
        req = _make_bounded_request(request_store)

        pkg = asyncio.run(
            execute_quickwit_request(
                req.evidence_request_id, request_store, connector,
                raw_store, masked_store, audit_logger, "ESESS-1",
            )
        )

        loaded = masked_store.load(pkg.evidence_id)
        assert loaded is not None
        assert loaded.evidence_id == pkg.evidence_id
        assert loaded.source_type == "quickwit_logs"


def test_execute_wrong_state_raises():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        request_store, connector, raw_store, masked_store, audit_logger = _setup(tmp_path)

        req = EvidenceRequest(
            evidence_session_id="ESESS-1",
            request_type="quickwit_query_plan",
            plan=_PLAN_DICT,
        )
        request_store.create(req)
        # Still in "created" state — not bounded

        try:
            asyncio.run(
                execute_quickwit_request(
                    req.evidence_request_id, request_store, connector,
                    raw_store, masked_store, audit_logger, "ESESS-1",
                )
            )
            assert False, "Should have raised ValueError"
        except ValueError as exc:
            assert "bounded" in str(exc).lower() or "created" in str(exc).lower()


def test_execute_transitions_to_failed_on_error():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        request_store, connector, raw_store, masked_store, audit_logger = _setup(tmp_path)

        # Create request with an invalid plan that can't be parsed into QuickwitQueryPlan
        req = EvidenceRequest(
            evidence_session_id="ESESS-1",
            request_type="quickwit_query_plan",
            plan={"type": "quickwit_query_plan", "bad_field": "nope"},
        )
        request_store.create(req)
        request_store.transition(req.evidence_request_id, "schema_checked")
        request_store.transition(req.evidence_request_id, "bounded")

        try:
            asyncio.run(
                execute_quickwit_request(
                    req.evidence_request_id, request_store, connector,
                    raw_store, masked_store, audit_logger, "ESESS-1",
                )
            )
            assert False, "Should have raised"
        except Exception:
            pass

        final = request_store.get(req.evidence_request_id)
        assert final.state == "failed"
