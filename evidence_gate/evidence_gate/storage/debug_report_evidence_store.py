from __future__ import annotations

import json
from pathlib import Path


class DebugReportEvidenceStore:
    """Persist per-debug-session artifacts the agent can cite in debug reports.

    The ``folder_id`` is the per-debug-session subdirectory under
    ``debug_reports/`` — by convention ``<JIRA_TICKET_ID>_<DEBUG_SESSION_ID>``
    (the DEBUG_SESSION_ID is the W3C OTel trace id minted in
    ``_start_debugging_session``). One debugging session = one directory, so
    every artifact lives together and is greppable by either id half.

    The four data-flow steps each leave a file keyed by ``EREQ-xxx`` (the
    evidence-request id) so the agent can cite the full chain from the debug
    report:

    - ``jira/sanitized_ticket.json`` — the sanitized Jira ticket context.
    - ``plans/<EREQ>.json`` — step 1: the agent's submitted plan, plus
      acceptance/rejection metadata. Written for both accepted and rejected
      plans.
    - ``translations/<EREQ>.json`` — step 2: the redacted translation of the
      plan into a source-specific query shape (Lucene filter shape or matched
      Metabase template). Resolved sensitive values are never written —
      ``value_ref`` placeholders are preserved.
    - ``executions/<EREQ>.json`` — step 3: source-query execution metadata
      (hit/row counts, ``evidence_id`` link). No raw data.
    - ``evidence/<EVID>.jsonl`` — step 4: redacted hits/rows (one record per
      line). Keyed by ``EVID-xxx``; the link from ``EREQ`` is in
      ``executions/<EREQ>.json``.
    - ``repos/...`` — agent-written repo-enumeration artifacts (out of scope
      for this store; the agent writes them directly).

    Paths are returned relative to project_root so the agent can drop them
    straight into a Markdown report (e.g. ``path:Lk``).

    Stays MASKED-only by contract — never feed raw connector rows here.
    """

    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root
        self._base = project_root / "debug_reports"

    def _rel(self, path: Path) -> str:
        try:
            return path.relative_to(self._project_root).as_posix()
        except ValueError:
            return str(path)

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

        return {
            "path": self._rel(path),
            "format": "jsonl",
            "line_count": len(lines),
        }

    def store_jira(self, folder_id: str, sanitized_ticket: dict) -> dict:
        """Persist the sanitized Jira ticket context under ``jira/``.

        Idempotent: a second call overwrites the existing file with the latest
        sanitized snapshot for that session.
        """
        jira_dir = self._base / folder_id / "jira"
        jira_dir.mkdir(parents=True, exist_ok=True)
        path = jira_dir / "sanitized_ticket.json"
        path.write_text(json.dumps(sanitized_ticket, indent=2, default=str, ensure_ascii=False))
        return {"path": self._rel(path), "format": "json"}

    def store_plan(
        self,
        folder_id: str,
        request_id: str,
        plan: dict,
        accepted: bool,
        rejection_reason: str = "",
        narrowing_applied: list[str] | None = None,
    ) -> dict:
        """Persist step 1: the agent's submitted plan under ``plans/``.

        Written for both accepted and rejected plans so the debug report has a
        complete record of what the agent tried — including replan loops.
        Keyed by ``request_id`` (e.g. ``EREQ-xxx``).
        """
        plans_dir = self._base / folder_id / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)
        path = plans_dir / f"{request_id}.json"
        body = {
            "evidence_request_id": request_id,
            "accepted": accepted,
            "rejection_reason": rejection_reason,
            "narrowing_applied": narrowing_applied or [],
            "plan": plan,
        }
        path.write_text(json.dumps(body, indent=2, default=str, ensure_ascii=False))
        return {"path": self._rel(path), "format": "json"}

    def store_translation(
        self, folder_id: str, request_id: str, translation: dict,
    ) -> dict:
        """Persist step 2: the redacted plan→query translation under
        ``translations/``.

        ``translation`` must describe the source query shape with
        ``value_ref`` placeholders preserved — never resolved sensitive
        values. Keyed by ``request_id``.
        """
        trans_dir = self._base / folder_id / "translations"
        trans_dir.mkdir(parents=True, exist_ok=True)
        path = trans_dir / f"{request_id}.json"
        path.write_text(json.dumps(translation, indent=2, default=str, ensure_ascii=False))
        return {"path": self._rel(path), "format": "json"}

    def store_execution(
        self, folder_id: str, request_id: str, execution: dict,
    ) -> dict:
        """Persist step 3: source-query execution metadata under ``executions/``.

        ``execution`` carries counts and the ``evidence_id`` link, never raw
        rows. Keyed by ``request_id``.
        """
        exec_dir = self._base / folder_id / "executions"
        exec_dir.mkdir(parents=True, exist_ok=True)
        path = exec_dir / f"{request_id}.json"
        path.write_text(json.dumps(execution, indent=2, default=str, ensure_ascii=False))
        return {"path": self._rel(path), "format": "json"}
