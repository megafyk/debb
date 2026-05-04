from __future__ import annotations

import httpx

from evidence_gate.app.config import Settings
from evidence_gate.audit.audit_logger import AuditLogger
from evidence_gate.connectors.auth import metabase_session_header
from evidence_gate.connectors.metabase_api_spec_loader import MetabaseApiSpecLoader
from evidence_gate.connectors.metabase_param_resolver import resolve_params
from evidence_gate.connectors.metabase_template_registry import DbTemplate, TemplateRegistry
from evidence_gate.contracts.query_plan import MetabaseQueryPlan
from evidence_gate.sessions.sensitive_value_store import SensitiveValueStore


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
        self._spec_loader = MetabaseApiSpecLoader()
        self._registry = TemplateRegistry()

    @property
    def is_live(self) -> bool:
        return bool(self._settings.metabase_url)

    async def execute(self, plan: MetabaseQueryPlan, evidence_session_id: str) -> list[dict]:
        """Execute a Metabase query via registered template.

        Returns raw result rows (stored in raw store, never exposed to agent).
        """
        template = self._registry.match(plan)
        if template is None:
            raise ValueError(
                f"No registered template for entity={plan.entity}, facts={plan.facts_requested}"
            )

        resolved = resolve_params(
            template, plan.params, evidence_session_id, self._sensitive_store
        )
        if resolved is None:
            raise ValueError("Failed to resolve template parameters")

        if self.is_live:
            rows = await self._execute_live(template, resolved)
        else:
            rows = self._fixture_rows(template, plan.facts_requested)

        self._audit.log(
            evidence_session_id,
            "metabase_query_executed",
            {"template_id": template.template_id, "row_count": len(rows)},
        )
        return rows

    async def _execute_live(self, template: DbTemplate, params: dict) -> list[dict]:
        headers = await metabase_session_header(self._settings)
        body = {
            "database": 1,
            "type": "native",
            "native": {
                "query": template.sql,
                "template-tags": {
                    name: {"name": name, "display-name": name, "type": "text", "required": True}
                    for name in template.param_names
                },
            },
            "parameters": [
                {"type": "text", "target": ["variable", ["template-tag", name]], "value": value}
                for name, value in params.items()
                if value != "__CONNECTOR_SECRET__"
            ],
        }
        async with httpx.AsyncClient() as client:
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
    def _fixture_rows(template: DbTemplate, facts_requested: list[str]) -> list[dict]:
        if template.entity == "account":
            return [{"status": "active", "locked": False, "disabled": False, "created_at": "2025-01-01"}]
        elif template.entity == "login_attempt":
            return [
                {"error_code": "PHONE_NORMALIZATION_FAILED", "cnt": 42},
                {"error_code": "ACCOUNT_LOOKUP_FAILED", "cnt": 15},
            ]
        return [{"result": "fixture_data"}]
