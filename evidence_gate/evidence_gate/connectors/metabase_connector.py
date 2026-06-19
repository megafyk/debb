"""Metabase connector — executes agent-provided SQL via Metabase native query API.

There is no template registry. The agent sends ``sql_candidate`` + ``params``
on each plan; safety/bounds checkers gate dangerous SQL before it reaches here,
and sensitive ``value_ref`` params are resolved from the sensitive store at
execute time so the agent never sees the raw values.
"""
from __future__ import annotations

import httpx

from evidence_gate.audit_logger import AuditLogger
from evidence_gate.config import Settings
from evidence_gate.connectors.auth import metabase_session_header
from evidence_gate.contracts import MetabaseQueryPlan
from evidence_gate.storage.sensitive_value_store import SensitiveValueStore


class MetabaseConnector:
    def __init__(
        self,
        settings: Settings,
        sensitive_store: SensitiveValueStore,
        audit_logger: AuditLogger,
    ) -> None:
        self._settings = settings
        self._sensitive_store = sensitive_store
        self._audit = audit_logger
        # Metabase session tokens are valid for days; cache and reuse across
        # queries so a burst of evidence requests doesn't trigger per-username
        # login throttling on /api/session. Refreshed on a 401.
        self._session_header: dict[str, str] | None = None

    async def _get_session_header(self) -> dict[str, str]:
        if self._session_header is None:
            self._session_header = await metabase_session_header(self._settings)
        return self._session_header

    @property
    def is_live(self) -> bool:
        return self._settings.metabase_enabled and bool(self._settings.metabase_url)

    async def execute(self, plan: MetabaseQueryPlan, evidence_session_id: str) -> list[dict]:
        """Run the agent's ``sql_candidate`` via Metabase native query.

        Returns raw result rows (stored in raw store, never exposed to agent).
        """
        if self.is_live:
            if not plan.sql_candidate:
                raise ValueError("plan.sql_candidate is required for live Metabase queries")
            if not plan.database_id:
                raise ValueError("plan.database_id is required for live Metabase queries")
            resolved = self._resolve_params(plan.params, evidence_session_id)
            rows = await self._execute_live(plan, resolved)
        else:
            rows = self._fixture_rows()

        self._audit.log(
            evidence_session_id,
            "metabase_query_executed",
            {"entity": plan.entity, "row_count": len(rows)},
        )
        return rows

    def _resolve_params(
        self,
        plan_params: list[dict],
        evidence_session_id: str,
    ) -> dict[str, str]:
        resolved: dict[str, str] = {}
        for pp in plan_params:
            name = pp.get("name")
            if not name:
                raise ValueError("each plan param requires a 'name'")
            if pp.get("value_ref"):
                value = self._sensitive_store.resolve(evidence_session_id, pp["value_ref"])
                if value is None:
                    raise ValueError(f"cannot resolve value_ref for param {name!r}")
                resolved[name] = value
            elif "value" in pp:
                resolved[name] = str(pp["value"])
            else:
                raise ValueError(f"param {name!r} has neither 'value' nor 'value_ref'")
        return resolved

    async def _execute_live(
        self, plan: MetabaseQueryPlan, params: dict[str, str]
    ) -> list[dict]:
        sql = plan.sql_candidate
        if plan.schema:
            sql = sql.replace("{schema}", plan.schema)
        body = {
            "database": plan.database_id,
            "type": "native",
            "native": {
                "query": sql,
                "template-tags": {
                    name: {"name": name, "display-name": name, "type": "text", "required": True}
                    for name in params
                },
            },
            "parameters": [
                {"type": "text", "target": ["variable", ["template-tag", name]], "value": value}
                for name, value in params.items()
            ],
        }
        url = f"{self._settings.metabase_url}/api/dataset"
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = await self._get_session_header()
            resp = await client.post(url, json=body, headers=headers)
            if resp.status_code == 401:
                # Session expired/revoked — re-login once and retry.
                self._session_header = None
                headers = await self._get_session_header()
                resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        # Metabase returns 2xx even when the query itself fails (syntax error,
        # missing table, permission denied), signalling failure only in the
        # body. Without this check a failed query looks like a successful empty
        # result and the agent reads a false "no matching records" signal.
        if data.get("error") or data.get("status") == "failed":
            raise RuntimeError(f"Metabase query failed: {data.get('error', 'unknown error')}")

        cols = [c["name"] for c in data.get("data", {}).get("cols", [])]
        rows_raw = data.get("data", {}).get("rows", [])
        return [dict(zip(cols, row)) for row in rows_raw]

    @staticmethod
    def _fixture_rows() -> list[dict]:
        return [{"result": "fixture_data"}]
