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
        headers = await metabase_session_header(self._settings)
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
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self._settings.metabase_url}/api/dataset",
                json=body,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        cols = [c["name"] for c in data.get("data", {}).get("cols", [])]
        rows_raw = data.get("data", {}).get("rows", [])
        return [dict(zip(cols, row)) for row in rows_raw]

    @staticmethod
    def _fixture_rows() -> list[dict]:
        return [{"result": "fixture_data"}]
