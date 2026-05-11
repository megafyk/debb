from __future__ import annotations

import json
from pathlib import Path


class DebugReportEvidenceStore:
    """Persist masked evidence as JSONL the agent can cite in debug reports.

    One masked record per line; line number == record index + 1. The path is
    returned relative to project_root so the agent can drop it straight into
    a Markdown report (e.g. ``path:Lk``) and any reader can navigate it.

    The ``folder_id`` is the per-debug-session subdirectory under
    ``debug_reports/`` — by convention ``<JIRA_TICKET_ID>_<DEBUG_SESSION_ID>``
    (the DEBUG_SESSION_ID is the W3C OTel trace id minted in
    ``_start_debugging_session``). One debugging session = one directory, so
    every artifact — masked evidence files written here, plus the
    agent-authored ``service_repo_map.md`` and ``debug_report.md`` (see
    debug-jira SKILL.md step 2) — lives together and is greppable by either
    id half. The caller (executor) builds the label; this store just writes
    there.

    Stays MASKED-only by contract — never feed raw connector rows here.
    """

    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root
        self._base = project_root / "debug_reports"

    def store(
        self,
        folder_id: str,
        evidence_id: str,
        masked_records: list[dict],
    ) -> dict:
        session_dir = self._base / folder_id / "evidence"
        session_dir.mkdir(parents=True, exist_ok=True)
        path = session_dir / f"{evidence_id}.jsonl"

        lines = [json.dumps(rec, default=str, ensure_ascii=False) for rec in masked_records]
        path.write_text("\n".join(lines) + ("\n" if lines else ""))

        try:
            rel = path.relative_to(self._project_root).as_posix()
        except ValueError:
            rel = str(path)

        return {
            "path": rel,
            "format": "jsonl",
            "line_count": len(lines),
        }
