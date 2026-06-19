"""Regression tests for the 2026-06-11 security/logic audit fixes.

Each test pins one confirmed finding so the gap can't silently reopen.
"""
from __future__ import annotations

import asyncio
import os
import stat
import tempfile
from pathlib import Path

import pytest

from evidence_gate.audit_logger import AuditLogger
from evidence_gate.config import Settings
from evidence_gate.connectors.metabase_connector import MetabaseConnector
import evidence_gate.connectors.metabase_connector as mb_mod
from evidence_gate.contracts import EvidenceRequest, EvidenceSession, MetabaseQueryPlan
from evidence_gate.mcp_server.tools import _start_debugging_session
from evidence_gate.redaction.jira_redactor import redact_value
from evidence_gate.request_services.bounds_checker import MAX_METABASE_ROWS, check_quickwit_bounds
from evidence_gate.request_services.content_safety_checker import check_plan_safety
from evidence_gate.request_services.evidence_executor import execute_metabase_request
from evidence_gate.request_services.report_reviewer import review_report
from evidence_gate.request_services.schema_checker import check_quickwit_plan
from evidence_gate.connectors.jira_connector import JiraConnector
from evidence_gate.storage.debug_report_evidence_store import DebugReportEvidenceStore
from evidence_gate.storage.evidence_request_store import EvidenceRequestStore
from evidence_gate.storage.evidence_session_store import EvidenceSessionStore
from evidence_gate.storage.json_store import JsonStore
from evidence_gate.storage.jsonl_event_store import JsonlEventStore
from evidence_gate.storage.masked_package_store import MaskedPackageStore
from evidence_gate.storage.raw_evidence_store import RawEvidenceStore
from evidence_gate.storage.sensitive_value_store import SensitiveValueStore


# ---- [0] Metabase {schema} substitution SQL-injection bypass ---------------

def test_safety_rejects_dangerous_schema_substitution():
    plan = {
        "sql_candidate": "SELECT id, status FROM {schema}.payments WHERE id = {{acct}}",
        "schema": "payments WHERE 1=1 UNION SELECT card_number FROM card_vault --",
        "params": [{"name": "acct", "value": "1"}],
    }
    result = check_plan_safety(plan)
    assert not result.ok
    # caught either as a non-identifier schema or via the post-substitution scan
    assert any("schema" in v or "injection" in v or "SELECT" in v for v in result.violations)


def test_safety_rejects_non_identifier_schema():
    result = check_plan_safety({"sql_candidate": "SELECT id FROM {schema}.t", "schema": "a; DROP TABLE t"})
    assert not result.ok


def test_safety_allows_bare_identifier_schema():
    plan = {"sql_candidate": "SELECT id FROM {schema}.account WHERE id = {{p}}", "schema": "public"}
    assert check_plan_safety(plan).ok


# ---- [1] Quickwit Lucene field-name injection ------------------------------

def test_schema_checker_rejects_injecting_field_name():
    plan = {
        "evidence_session_id": "ESESS-1", "service": "svc", "datasource_uid": "ds",
        "from": "2026-01-01T00:00:00+00:00", "to": "2026-01-01T01:00:00+00:00",
        "query_intent": "x", "fields_requested": ["timestamp"], "max_hits": 10,
        "filters": [{"field": "level:error OR service", "op": "=", "value": "x"}],
    }
    result = check_quickwit_plan(plan)
    assert not result.ok
    assert any("field" in e for e in result.errors)


def test_schema_checker_allows_dotted_and_slash_fields():
    plan = {
        "evidence_session_id": "ESESS-1", "service": "svc", "datasource_uid": "ds",
        "from": "2026-01-01T00:00:00+00:00", "to": "2026-01-01T01:00:00+00:00",
        "query_intent": "x", "fields_requested": ["timestamp"], "max_hits": 10,
        "filters": [
            {"field": "contextMap.traceId", "op": "=", "value": "x"},
            {"field": "kubernetes.labels.app_kubernetes_io/instance", "op": "=", "value": "y"},
        ],
    }
    assert check_quickwit_plan(plan).ok


# ---- [2] Safety/report PII patterns out of sync with the redactor ----------

@pytest.mark.parametrize("msisdn", ["84974515324", "0974515324"])
def test_safety_rejects_vietnamese_msisdn(msisdn):
    result = check_plan_safety({"query_intent": f"login fails for {msisdn}"})
    assert not result.ok


def test_report_review_rejects_vietnamese_msisdn():
    report = {
        "ticket_id": "BUG-1", "evidence_session_id": "ESESS-1",
        "summary": "Login fails for msisdn 84974515324",
        "most_likely_root_cause": "x", "confidence": "low",
        "evidence_ids": ["EVID-1"], "audit_refs": ["AUD-1"], "verification_steps": ["check"],
    }
    result = review_report(report)
    assert not result.ok
    assert any("phone" in i for i in result.issues)


def test_report_review_rejects_token_assignment():
    report = {
        "ticket_id": "BUG-1", "evidence_session_id": "ESESS-1",
        "summary": "token: abc123def456ghi789",
        "most_likely_root_cause": "x", "confidence": "low",
        "evidence_ids": ["EVID-1"], "audit_refs": ["AUD-1"], "verification_steps": ["check"],
    }
    assert not review_report(report).ok


# ---- [3] Metabase query failure must not look like an empty success --------

def _live_metabase(monkeypatch, response_body):
    settings = Settings(metabase_enabled=True, metabase_url="http://mb.local",
                        metabase_username="u", metabase_password="p")
    connector = MetabaseConnector(settings, SensitiveValueStore(Path(tempfile.mkdtemp())),
                                  AuditLogger(JsonlEventStore(Path(tempfile.mkdtemp()) / "a.jsonl")))

    async def _fake_header():
        return {"X-Metabase-Session": "s"}
    monkeypatch.setattr(connector, "_get_session_header", _fake_header)

    class FakeResponse:
        status_code = 200
        def raise_for_status(self): return None
        def json(self): return response_body

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None
        async def post(self, *a, **k): return FakeResponse()

    monkeypatch.setattr(mb_mod.httpx, "AsyncClient", FakeClient)
    return connector


def test_metabase_failed_query_raises(monkeypatch):
    connector = _live_metabase(monkeypatch, {"status": "failed", "error": "syntax error",
                                             "data": {"rows": [], "cols": []}})
    plan = MetabaseQueryPlan(evidence_session_id="ESESS-1", service="s", entity="account",
                             query_intent="x", facts_requested=["f"],
                             sql_candidate="SELECT id FROM account WHERE id = {{p}}",
                             params=[{"name": "p", "value": "1"}], database_id=1)
    with pytest.raises(RuntimeError):
        asyncio.run(connector.execute(plan, "ESESS-1"))


def test_metabase_ok_query_returns_rows(monkeypatch):
    connector = _live_metabase(monkeypatch, {"data": {"cols": [{"name": "id"}], "rows": [[1], [2]]}})
    plan = MetabaseQueryPlan(evidence_session_id="ESESS-1", service="s", entity="account",
                             query_intent="x", facts_requested=["f"],
                             sql_candidate="SELECT id FROM account WHERE id = {{p}}",
                             params=[{"name": "p", "value": "1"}], database_id=1)
    rows = asyncio.run(connector.execute(plan, "ESESS-1"))
    assert rows == [{"id": 1}, {"id": 2}]


# ---- [4] trace_id path traversal -------------------------------------------

def _tool_deps(tmp_path: Path):
    return (
        EvidenceSessionStore(tmp_path), SensitiveValueStore(tmp_path),
        AuditLogger(JsonlEventStore(tmp_path / "audit.jsonl")), JiraConnector(),
        DebugReportEvidenceStore(tmp_path),
    )


@pytest.mark.parametrize("bad", ["../../etc/passwd", "a/b", "a\\b", "..", "x" * 65])
def test_start_session_rejects_traversal_trace_id(bad):
    with tempfile.TemporaryDirectory() as tmp:
        deps = _tool_deps(Path(tmp))
        with pytest.raises(ValueError):
            asyncio.run(_start_debugging_session("BUG-123", bad, "", *deps))


def test_start_session_accepts_hex_trace_id():
    with tempfile.TemporaryDirectory() as tmp:
        deps = _tool_deps(Path(tmp))
        result = asyncio.run(
            _start_debugging_session("BUG-123", "4bf92f3577b34da6a3ce929d0e0e4736", "", *deps)
        )
        assert result  # no raise


# ---- [5] redact_value must redact dict keys --------------------------------

def test_redact_value_redacts_dict_keys():
    out = redact_value({"84974515324": {"x": 1}, "user@evil.com": "y"})
    assert "84974515324" not in out
    assert "user@evil.com" not in out
    assert any("REDACTED" in k for k in out)


# ---- [6] raw-data stores are owner-only ------------------------------------

def test_sensitive_store_files_are_owner_only():
    with tempfile.TemporaryDirectory() as tmp:
        store = SensitiveValueStore(Path(tmp))
        ref = store.store("ESESS-1", "phone", "84974515324")
        path = Path(tmp) / "sensitive_values" / "ESESS-1.json"
        mode = stat.S_IMODE(os.stat(path).st_mode)
        assert mode == 0o600
        dir_mode = stat.S_IMODE(os.stat(path.parent).st_mode)
        assert dir_mode == 0o700
        assert store.resolve("ESESS-1", ref) == "84974515324"


def test_raw_evidence_files_are_owner_only():
    with tempfile.TemporaryDirectory() as tmp:
        store = RawEvidenceStore(Path(tmp))
        store.store("EREQ-1", [{"a": 1}])
        path = Path(tmp) / "raw_evidence" / "EREQ-1.json"
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


# ---- [7] mixed naive/aware datetimes must not crash bounds -----------------

def test_bounds_mixed_naive_aware_no_crash():
    plan = {
        "from": "2026-01-01T00:00:00",          # naive
        "to": "2026-01-01T02:00:00+00:00",      # aware
        "max_hits": 100,
        "filters": [{"field": "service", "op": "=", "value": "svc"}],
    }
    result = check_quickwit_bounds(plan)  # must not raise TypeError
    assert result.ok


def test_bounds_mixed_naive_aware_detects_inverted_window():
    plan = {
        "from": "2026-01-02T00:00:00",
        "to": "2026-01-01T00:00:00+00:00",
        "max_hits": 100,
        "filters": [{"field": "service", "op": "=", "value": "svc"}],
    }
    result = check_quickwit_bounds(plan)
    assert not result.ok


# ---- [8] Metabase result-volume cap ----------------------------------------

def _executor_setup(tmp_path: Path, rows: list[dict]):
    settings = Settings(metabase_url="", metabase_username="", metabase_password="")
    audit_logger = AuditLogger(JsonlEventStore(tmp_path / "audit.jsonl"))
    connector = MetabaseConnector(settings, SensitiveValueStore(tmp_path), audit_logger)

    async def _fake_execute(plan, sid):
        return rows
    connector.execute = _fake_execute  # type: ignore[method-assign]

    request_store = EvidenceRequestStore(JsonStore(tmp_path, "requests"), audit_logger)
    session_store = EvidenceSessionStore(tmp_path)
    session_store.save(EvidenceSession(evidence_session_id="ESESS-1", ticket_id="BUG-1",
                                       trace_id="4bf92f3577b34da6a3ce929d0e0e4736"))
    req = EvidenceRequest(evidence_session_id="ESESS-1", request_type="metabase_query_plan",
                          plan={"type": "metabase_query_plan", "evidence_session_id": "ESESS-1",
                                "service": "s", "entity": "account", "query_intent": "x",
                                "facts_requested": ["f"]})
    request_store.create(req)
    request_store.transition(req.evidence_request_id, "schema_checked")
    request_store.transition(req.evidence_request_id, "bounded")
    return (req, request_store, connector, RawEvidenceStore(tmp_path),
            MaskedPackageStore(tmp_path), DebugReportEvidenceStore(tmp_path),
            session_store, audit_logger)


def test_metabase_rows_capped_to_max():
    with tempfile.TemporaryDirectory() as tmp:
        many = [{"id": i} for i in range(MAX_METABASE_ROWS + 50)]
        req, rs, conn, raw, masked, dr, ss, al = _executor_setup(Path(tmp), many)
        pkg = asyncio.run(execute_metabase_request(
            req.evidence_request_id, rs, conn, raw, masked, dr, ss, al, "ESESS-1"))
        assert pkg.masked_data["row_count"] == MAX_METABASE_ROWS
        # full raw set still retained server-side
        assert len(raw.load(req.evidence_request_id)) == MAX_METABASE_ROWS + 50


# ---- [9] Quickwit must not silently fall back to match-all -----------------

def test_quickwit_refuses_when_all_filters_drop(monkeypatch):
    from evidence_gate.contracts import QueryFilter, QuickwitQueryPlan
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        connector = __import__("evidence_gate.connectors.quickwit_connector",
                               fromlist=["QuickwitConnector"]).QuickwitConnector(
            Settings(quickwit_url="", quickwit_username="", quickwit_password=""),
            SensitiveValueStore(tmp_path),
            AuditLogger(JsonlEventStore(tmp_path / "a.jsonl")),
        )
        plan = QuickwitQueryPlan(
            evidence_session_id="ESESS-1", service="svc", datasource_uid="ds",
            from_="2026-01-01T00:00:00+00:00", to="2026-01-01T01:00:00+00:00",
            query_intent="x", fields_requested=["timestamp"], max_hits=10,
            filters=[QueryFilter(field="user", op="matches_sensitive_ref", value_ref="MISSING_REF")],
        )
        with pytest.raises(ValueError):
            connector._build_search_body(plan, "ESESS-1")
