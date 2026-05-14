from __future__ import annotations

import json
import tempfile
from pathlib import Path

from evidence_gate.storage.debug_report_evidence_store import DebugReportEvidenceStore

# Conventional folder shape: <JIRA_TICKET_ID>_<DEBUG_SESSION_ID> — the
# DEBUG_SESSION_ID is the W3C OTel trace id (32 lowercase hex chars,
# W3C trace-context §3.2.2.3) carried on the EvidenceSession.
_FOLDER = "BUG-1_4bf92f3577b34da6a3ce929d0e0e4736"
_OTHER = "BUG-2_00f067aa0ba902b7000000000000abcd"


def test_store_writes_jsonl_one_record_per_line():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = DebugReportEvidenceStore(root)
        records = [
            {"message": "first", "level": "INFO"},
            {"message": "second", "level": "WARN"},
            {"message": "third", "level": "ERROR"},
        ]

        ref = store.store(_FOLDER, "EVID-xyz", records)

        out = root / "debug_reports" / _FOLDER / "evidence" / "EVID-xyz.jsonl"
        assert out.exists()
        lines = out.read_text().splitlines()
        assert len(lines) == 3
        assert json.loads(lines[0]) == records[0]
        assert json.loads(lines[2]) == records[2]

        assert ref == {
            "path": f"debug_reports/{_FOLDER}/evidence/EVID-xyz.jsonl",
            "format": "jsonl",
            "line_count": 3,
        }


def test_store_empty_records_writes_empty_file_and_reports_zero_lines():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = DebugReportEvidenceStore(root)

        ref = store.store(_FOLDER, "EVID-empty", [])

        out = root / "debug_reports" / _FOLDER / "evidence" / "EVID-empty.jsonl"
        assert out.exists()
        assert out.read_text() == ""
        assert ref["line_count"] == 0
        assert ref["format"] == "jsonl"


def test_store_groups_by_folder_id():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = DebugReportEvidenceStore(root)

        store.store(_FOLDER, "EVID-1", [{"x": 1}])
        store.store(_FOLDER, "EVID-2", [{"x": 2}])
        store.store(_OTHER, "EVID-3", [{"x": 3}])

        a = sorted(p.name for p in (root / "debug_reports" / _FOLDER / "evidence").iterdir())
        b = sorted(p.name for p in (root / "debug_reports" / _OTHER / "evidence").iterdir())
        assert a == ["EVID-1.jsonl", "EVID-2.jsonl"]
        assert b == ["EVID-3.jsonl"]


def test_path_is_relative_to_project_root_for_agent_citation():
    """Returned path must be relative so it drops cleanly into a Markdown report."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = DebugReportEvidenceStore(root)

        ref = store.store(_FOLDER, "EVID-1", [{"a": 1}])

        # Path must not be absolute and must not contain the tmp prefix.
        assert not ref["path"].startswith("/")
        assert tmp not in ref["path"]
        assert ref["path"].startswith(f"debug_reports/{_FOLDER}/")


def test_store_jira_writes_sanitized_ticket_under_jira_subdir():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = DebugReportEvidenceStore(root)

        ticket = {
            "ticket_id": "BUG-1",
            "summary": "login fails",
            "description_sanitized": "[SECURE_VALUE_REF_phone_number_abc] cannot log in",
        }
        ref = store.store_jira(_FOLDER, ticket)

        out = root / "debug_reports" / _FOLDER / "jira" / "sanitized_ticket.json"
        assert out.exists()
        assert json.loads(out.read_text()) == ticket
        assert ref == {
            "path": f"debug_reports/{_FOLDER}/jira/sanitized_ticket.json",
            "format": "json",
        }


def test_store_jira_overwrites_existing_snapshot():
    """Re-entry of a session must refresh the file rather than appending."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = DebugReportEvidenceStore(root)

        store.store_jira(_FOLDER, {"summary": "old"})
        store.store_jira(_FOLDER, {"summary": "new"})

        out = root / "debug_reports" / _FOLDER / "jira" / "sanitized_ticket.json"
        assert json.loads(out.read_text()) == {"summary": "new"}


def test_store_plan_writes_accepted_plan_with_metadata_under_plans_subdir():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = DebugReportEvidenceStore(root)

        plan = {
            "type": "quickwit_query_plan",
            "evidence_session_id": "ESESS-1",
            "service": "auth",
            "filters": [{"field": "msisdn", "op": "=", "value": "1234"}],
        }
        ref = store.store_plan(
            _FOLDER, "EREQ-abc12345", plan,
            accepted=True, narrowing_applied=["max_hits truncated 1000->100"],
        )

        out = root / "debug_reports" / _FOLDER / "plans" / "EREQ-abc12345.json"
        assert out.exists()
        body = json.loads(out.read_text())
        assert body["evidence_request_id"] == "EREQ-abc12345"
        assert body["accepted"] is True
        assert body["rejection_reason"] == ""
        assert body["narrowing_applied"] == ["max_hits truncated 1000->100"]
        assert body["plan"] == plan
        assert ref == {
            "path": f"debug_reports/{_FOLDER}/plans/EREQ-abc12345.json",
            "format": "json",
        }


def test_store_plan_records_rejection_reason_for_rejected_plans():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = DebugReportEvidenceStore(root)

        ref = store.store_plan(
            _FOLDER, "EREQ-bad", {"type": "quickwit_query_plan"},
            accepted=False, rejection_reason="safety: email pattern in query_intent",
        )

        out = root / "debug_reports" / _FOLDER / "plans" / "EREQ-bad.json"
        body = json.loads(out.read_text())
        assert body["accepted"] is False
        assert body["rejection_reason"] == "safety: email pattern in query_intent"
        assert ref["path"].endswith("plans/EREQ-bad.json")


def test_store_plan_keyed_by_request_id_and_groups_per_session():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = DebugReportEvidenceStore(root)

        store.store_plan(_FOLDER, "EREQ-1", {"q": 1}, accepted=True)
        store.store_plan(_FOLDER, "EREQ-2", {"q": 2}, accepted=True)
        store.store_plan(_OTHER, "EREQ-3", {"q": 3}, accepted=True)

        a = sorted(p.name for p in (root / "debug_reports" / _FOLDER / "plans").iterdir())
        b = sorted(p.name for p in (root / "debug_reports" / _OTHER / "plans").iterdir())
        assert a == ["EREQ-1.json", "EREQ-2.json"]
        assert b == ["EREQ-3.json"]


def test_store_translation_writes_under_translations_subdir():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = DebugReportEvidenceStore(root)

        translation = {
            "translation_type": "quickwit_lucene",
            "datasource_uid": "login-service-prod",
            "lucene_filter_shape": [
                {"field": "user_id", "op": "matches_sensitive_ref", "value_ref": "SVR-xyz"},
            ],
            "max_hits": 100,
        }
        ref = store.store_translation(_FOLDER, "EREQ-abc12345", translation)

        out = root / "debug_reports" / _FOLDER / "translations" / "EREQ-abc12345.json"
        assert out.exists()
        assert json.loads(out.read_text()) == translation
        assert ref == {
            "path": f"debug_reports/{_FOLDER}/translations/EREQ-abc12345.json",
            "format": "json",
        }


def test_store_execution_writes_under_executions_subdir_with_evidence_link():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = DebugReportEvidenceStore(root)

        execution = {
            "evidence_request_id": "EREQ-abc12345",
            "source_type": "quickwit_grafana_proxy",
            "hit_count": 7,
            "evidence_id": "EVID-xyz789",
        }
        ref = store.store_execution(_FOLDER, "EREQ-abc12345", execution)

        out = root / "debug_reports" / _FOLDER / "executions" / "EREQ-abc12345.json"
        assert out.exists()
        body = json.loads(out.read_text())
        assert body["evidence_id"] == "EVID-xyz789"
        assert body["hit_count"] == 7
        assert ref["path"].endswith("executions/EREQ-abc12345.json")
