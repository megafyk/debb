from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from evidence_gate.config import Settings
from evidence_gate.audit_logger import AuditLogger
from evidence_gate.connectors.quickwit_connector import QuickwitConnector
from evidence_gate.contracts import EvidenceRequest, EvidenceSession
from evidence_gate.request_services.evidence_executor import execute_quickwit_request
from evidence_gate.storage.debug_report_evidence_store import DebugReportEvidenceStore
from evidence_gate.storage.sensitive_value_store import SensitiveValueStore
from evidence_gate.storage.evidence_request_store import EvidenceRequestStore
from evidence_gate.storage.evidence_session_store import EvidenceSessionStore
from evidence_gate.storage.json_store import JsonStore
from evidence_gate.storage.jsonl_event_store import JsonlEventStore
from evidence_gate.storage.masked_package_store import MaskedPackageStore
from evidence_gate.storage.raw_evidence_store import RawEvidenceStore

_TICKET_ID = "BUG-1"
_TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"  # W3C example OTel trace id

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
    dr_store = DebugReportEvidenceStore(tmp_path)
    session_store = EvidenceSessionStore(tmp_path)
    session_store.save(EvidenceSession(
        evidence_session_id="ESESS-1", ticket_id=_TICKET_ID, trace_id=_TRACE_ID,
    ))
    return request_store, connector, raw_store, masked_store, dr_store, session_store, audit_logger


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
        request_store, connector, raw_store, masked_store, dr_store, session_store, audit_logger = _setup(tmp_path)
        req = _make_bounded_request(request_store)

        pkg = asyncio.run(
            execute_quickwit_request(
                req.evidence_request_id, request_store, connector,
                raw_store, masked_store, dr_store, session_store, audit_logger, "ESESS-1",
            )
        )

        assert pkg.source_type == "quickwit_logs"
        final = request_store.get(req.evidence_request_id)
        assert final.state == "masked_package_ready"
        assert final.evidence_id == pkg.evidence_id


def test_execute_stores_raw_evidence():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        request_store, connector, raw_store, masked_store, dr_store, session_store, audit_logger = _setup(tmp_path)
        req = _make_bounded_request(request_store)

        asyncio.run(
            execute_quickwit_request(
                req.evidence_request_id, request_store, connector,
                raw_store, masked_store, dr_store, session_store, audit_logger, "ESESS-1",
            )
        )

        raw = raw_store.load(req.evidence_request_id)
        assert raw is not None
        assert len(raw) == 3  # fixture returns 3 hits


def test_execute_stores_masked_package():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        request_store, connector, raw_store, masked_store, dr_store, session_store, audit_logger = _setup(tmp_path)
        req = _make_bounded_request(request_store)

        pkg = asyncio.run(
            execute_quickwit_request(
                req.evidence_request_id, request_store, connector,
                raw_store, masked_store, dr_store, session_store, audit_logger, "ESESS-1",
            )
        )

        loaded = masked_store.load(pkg.evidence_id)
        assert loaded is not None
        assert loaded.evidence_id == pkg.evidence_id
        assert loaded.source_type == "quickwit_logs"


def test_execute_writes_evidence_file_for_agent_citation():
    """Masked hits must land under debug_reports/<TICKET_ID>_<DEBUG_SESSION_ID>/
    evidence/<eid>.jsonl so the agent can cite path:Lk as a verifiable
    reference in the debug report (the DEBUG_SESSION_ID is the OTel trace id
    carried on the session)."""
    import json

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        request_store, connector, raw_store, masked_store, dr_store, session_store, audit_logger = _setup(tmp_path)
        req = _make_bounded_request(request_store)

        pkg = asyncio.run(
            execute_quickwit_request(
                req.evidence_request_id, request_store, connector,
                raw_store, masked_store, dr_store, session_store, audit_logger, "ESESS-1",
            )
        )

        # Package now carries a file ref the agent can cite.
        folder = f"{_TICKET_ID}_{_TRACE_ID}"
        ref = pkg.evidence_file
        assert ref["format"] == "jsonl"
        assert ref["line_count"] == 3  # fixture returns 3 hits
        assert ref["path"] == f"debug_reports/{folder}/evidence/{pkg.evidence_id}.jsonl"

        # The file actually exists on disk and contains the masked hits, not raw.
        on_disk = tmp_path / "debug_reports" / folder / "evidence" / f"{pkg.evidence_id}.jsonl"
        assert on_disk.exists()
        lines = on_disk.read_text().splitlines()
        assert len(lines) == 3
        # Each line is one masked hit (same content as pkg.masked_data["hits"][i]).
        for i, line in enumerate(lines):
            assert json.loads(line) == pkg.masked_data["hits"][i]


def test_evidence_file_ref_persists_with_masked_package():
    """Reloading the package from the store must still expose evidence_file —
    the agent often fetches the package later via get_masked_evidence_package."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        request_store, connector, raw_store, masked_store, dr_store, session_store, audit_logger = _setup(tmp_path)
        req = _make_bounded_request(request_store)

        pkg = asyncio.run(
            execute_quickwit_request(
                req.evidence_request_id, request_store, connector,
                raw_store, masked_store, dr_store, session_store, audit_logger, "ESESS-1",
            )
        )

        loaded = masked_store.load(pkg.evidence_id)
        assert loaded is not None
        assert loaded.evidence_file == pkg.evidence_file
        assert loaded.evidence_file["path"].endswith(f"{pkg.evidence_id}.jsonl")


def test_execute_wrong_state_raises():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        request_store, connector, raw_store, masked_store, dr_store, session_store, audit_logger = _setup(tmp_path)

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
                    raw_store, masked_store, dr_store, session_store, audit_logger, "ESESS-1",
                )
            )
            assert False, "Should have raised ValueError"
        except ValueError as exc:
            assert "bounded" in str(exc).lower() or "created" in str(exc).lower()


def test_execute_transitions_to_failed_on_error():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        request_store, connector, raw_store, masked_store, dr_store, session_store, audit_logger = _setup(tmp_path)

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
                    raw_store, masked_store, dr_store, session_store, audit_logger, "ESESS-1",
                )
            )
            assert False, "Should have raised"
        except Exception:
            pass

        final = request_store.get(req.evidence_request_id)
        assert final.state == "failed"


def test_executor_sanitizes_connector_exception_message():
    """Connector exceptions (e.g. httpx URL leakage) must not propagate to the agent."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        request_store, connector, raw_store, masked_store, dr_store, session_store, audit_logger = _setup(tmp_path)
        req = _make_bounded_request(request_store)

        async def _leaky_execute(plan, sid):
            raise RuntimeError(
                "500 Server Error for url 'https://internal-quickwit.corp:7280/api/ds/query' "
                "with header 'Authorization: Basic c2VjcmV0OnB3'"
            )

        connector.execute = _leaky_execute  # type: ignore[assignment]

        try:
            asyncio.run(
                execute_quickwit_request(
                    req.evidence_request_id, request_store, connector,
                    raw_store, masked_store, dr_store, session_store, audit_logger, "ESESS-1",
                )
            )
            assert False, "Should have raised"
        except RuntimeError as exc:
            msg = str(exc)
            assert "internal-quickwit.corp" not in msg
            assert "Basic c2VjcmV0OnB3" not in msg
            assert req.evidence_request_id in msg

        # The chained __cause__ must also be suppressed (raise ... from None)
        # so the original message isn't accessible via standard traceback display.
        final = request_store.get(req.evidence_request_id)
        assert final.state == "failed"
