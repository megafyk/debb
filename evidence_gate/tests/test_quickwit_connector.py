from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from evidence_gate.config import Settings
from evidence_gate.audit_logger import AuditLogger
from evidence_gate.connectors.quickwit_connector import QuickwitConnector
from evidence_gate.contracts import QuickwitQueryPlan, QueryFilter
from evidence_gate.storage.sensitive_value_store import SensitiveValueStore
from evidence_gate.storage.jsonl_event_store import JsonlEventStore


def _make_plan(**overrides: object) -> QuickwitQueryPlan:
    defaults = dict(
        type="quickwit_query_plan",
        evidence_session_id="ESESS-1",
        service="login-service",
        datasource_uid="login-service-prod",
        from_="2026-01-01T00:00:00+00:00",
        to="2026-01-01T02:00:00+00:00",
        query_intent="Find login failures",
        filters=[QueryFilter(field="error_code", op="=", value="ACCOUNT_LOOKUP_FAILED")],
        fields_requested=["timestamp", "error_code", "trace_id"],
        max_hits=100,
    )
    defaults.update(overrides)
    return QuickwitQueryPlan(**defaults)


def _setup(tmp_path: Path):
    settings = Settings(quickwit_url="", quickwit_username="", quickwit_password="")
    sensitive_store = SensitiveValueStore(tmp_path)
    audit_logger = AuditLogger(JsonlEventStore(tmp_path / "audit.jsonl"))
    connector = QuickwitConnector(settings, sensitive_store, audit_logger)
    return connector, settings, sensitive_store, audit_logger


def test_fixture_mode_returns_hits():
    with tempfile.TemporaryDirectory() as tmp:
        connector, _, _, _ = _setup(Path(tmp))
        plan = _make_plan()
        result = asyncio.run(connector.execute(plan, "ESESS-1"))
        assert result.is_valuable is True
        assert result.reason == ""
        assert len(result.hits) == 3
        for hit in result.hits:
            for field in plan.fields_requested:
                assert field in hit


def test_is_live_false_when_no_url():
    with tempfile.TemporaryDirectory() as tmp:
        connector, _, _, _ = _setup(Path(tmp))
        assert connector.is_live is False


def test_is_live_true_when_url_set():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        settings = Settings(quickwit_url="http://localhost:7280", quickwit_username="", quickwit_password="")
        sensitive_store = SensitiveValueStore(tmp_path)
        audit_logger = AuditLogger(JsonlEventStore(tmp_path / "audit.jsonl"))
        connector = QuickwitConnector(settings, sensitive_store, audit_logger)
        assert connector.is_live is True


def test_build_search_body_filters():
    with tempfile.TemporaryDirectory() as tmp:
        connector, _, _, _ = _setup(Path(tmp))
        plan = _make_plan(
            filters=[
                QueryFilter(field="error_code", op="=", value="ACCOUNT_LOOKUP_FAILED"),
                QueryFilter(field="level", op="in", value=["ERROR", "WARN"]),
                QueryFilter(field="message", op="contains", value="timeout"),
            ]
        )
        body = connector._build_search_body(plan, "ESESS-1")
        assert "from" in body and "to" in body
        assert len(body["queries"]) == 1
        sub = body["queries"][0]
        assert sub["refId"] == "A"
        assert sub["datasource"] == {
            "type": "quickwit-quickwit-datasource",
            "uid": "login-service-prod",
        }
        assert sub["metrics"] == [
            {
                "type": "logs",
                "id": "1",
                "settings": {"limit": "100", "sortDirection": "desc"},
            }
        ]
        assert sub["bucketAggs"] == []
        assert sub["timeField"] == ""
        assert sub["alias"] == ""
        query = sub["query"]
        assert 'error_code:"ACCOUNT_LOOKUP_FAILED"' in query
        assert '(level:"ERROR" OR level:"WARN")' in query
        assert 'message:"timeout"' in query
        assert " AND " in query


def test_build_search_body_skips_op_in_with_empty_value_list():
    # Defensive: `op:"in"` with an empty value list would emit the invalid
    # Lucene fragment `()` and break the whole query. The filter should be
    # skipped instead, leaving the other terms intact.
    with tempfile.TemporaryDirectory() as tmp:
        connector, _, _, _ = _setup(Path(tmp))
        plan = _make_plan(
            filters=[
                QueryFilter(field="service", op="=", value="auth"),
                QueryFilter(field="level", op="in", value=[]),
            ]
        )
        body = connector._build_search_body(plan, "ESESS-1")
        query = body["queries"][0]["query"]
        assert 'service:"auth"' in query
        assert "()" not in query
        assert "level:" not in query


def test_build_search_body_escapes_slash_in_field_name():
    # Field names like `kubernetes.labels.app_kubernetes_io/instance` were
    # rejected by Quickwit because Lucene treats `/` as a reserved regex
    # delimiter unless escaped.
    with tempfile.TemporaryDirectory() as tmp:
        connector, _, _, _ = _setup(Path(tmp))
        plan = _make_plan(filters=[QueryFilter(
            field="kubernetes.labels.app_kubernetes_io/instance",
            op="=",
            value="production-cdcn-auth-service",
        )])
        query = connector._build_search_body(plan, "ESESS-1")["queries"][0]["query"]
        assert 'kubernetes.labels.app_kubernetes_io\\/instance:"production-cdcn-auth-service"' in query


def test_build_search_body_contains_multiword_uses_and_of_tokens():
    # Multi-word `contains` as a phrase query (`message:"a b c"`) fails on
    # fields whose analyzer doesn't index positions. AND-of-tokens preserves
    # "this literal appears in the field" semantics.
    with tempfile.TemporaryDirectory() as tmp:
        connector, _, _, _ = _setup(Path(tmp))
        plan = _make_plan(filters=[QueryFilter(
            field="message", op="contains", value="Max send otp",
        )])
        query = connector._build_search_body(plan, "ESESS-1")["queries"][0]["query"]
        assert '(message:"Max" AND message:"send" AND message:"otp")' in query


def test_build_search_body_sensitive_ref():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        connector, _, sensitive_store, _ = _setup(tmp_path)
        ref = sensitive_store.store("ESESS-1", "email", "admin@corp.com")
        plan = _make_plan(
            filters=[QueryFilter(field="user_email", op="matches_sensitive_ref", value_ref=ref)]
        )
        body = connector._build_search_body(plan, "ESESS-1")
        assert "admin@corp.com" in body["queries"][0]["query"]


def test_live_request_includes_org_and_plugin_headers(monkeypatch):
    captured: dict = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"results": {"A": {"frames": []}}}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json, headers):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return FakeResponse()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        settings = Settings(
            quickwit_url="http://grafana.local",
            quickwit_username="u",
            quickwit_password="p",
            quickwit_org_id=2,
        )
        sensitive_store = SensitiveValueStore(tmp_path)
        audit_logger = AuditLogger(JsonlEventStore(tmp_path / "audit.jsonl"))
        connector = QuickwitConnector(settings, sensitive_store, audit_logger)

        import evidence_gate.connectors.quickwit_connector as qc_mod

        monkeypatch.setattr(qc_mod.httpx, "AsyncClient", FakeClient)

        plan = _make_plan()
        asyncio.run(connector.execute(plan, "ESESS-1"))

    assert captured["url"] == "http://grafana.local/api/ds/query"
    assert captured["headers"]["X-Grafana-Org-Id"] == "2"
    assert captured["headers"]["x-plugin-id"] == "quickwit-quickwit-datasource"
    assert captured["headers"]["x-datasource-uid"] == "login-service-prod"
    assert captured["json"]["queries"][0]["datasource"]["type"] == "quickwit-quickwit-datasource"


def test_audit_logged_after_execute():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        event_store = JsonlEventStore(tmp_path / "audit.jsonl")
        audit_logger = AuditLogger(event_store)
        settings = Settings(quickwit_url="", quickwit_username="", quickwit_password="")
        sensitive_store = SensitiveValueStore(tmp_path)
        connector = QuickwitConnector(settings, sensitive_store, audit_logger)

        plan = _make_plan()
        asyncio.run(connector.execute(plan, "ESESS-1"))

        events = event_store.read_all()
        qw_events = [e for e in events if e.get("event_type") == "quickwit_query_executed"]
        assert len(qw_events) >= 1
