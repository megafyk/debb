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
