"""Metabase connector — runs only registered SQL templates."""
from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from evidence_gate.audit_logger import AuditLogger
from evidence_gate.config import Settings
from evidence_gate.connectors.auth import metabase_session_header
from evidence_gate.contracts import MetabaseQueryPlan
from evidence_gate.storage.sensitive_value_store import SensitiveValueStore


# ---- Template registry -----------------------------------------------------

@dataclass
class DbTemplate:
    template_id: str
    entity: str
    description: str
    sql: str
    param_names: list[str]
    facts_produced: list[str] = field(default_factory=list)


_TEMPLATES: dict[str, DbTemplate] = {
    "account_status_by_phone_hash": DbTemplate(
        template_id="account_status_by_phone_hash",
        entity="account",
        description="Account status lookup by phone hash",
        sql=(
            "SELECT status, locked, disabled, created_at "
            "FROM account "
            "WHERE phone_hash = HMAC_SHA256(:phone_number, :tenant_salt) "
            "LIMIT 1"
        ),
        param_names=["phone_number", "tenant_salt"],
        facts_produced=["account_exists", "account_status", "is_locked", "is_disabled"],
    ),
    "account_status_by_email_hash": DbTemplate(
        template_id="account_status_by_email_hash",
        entity="account",
        description="Account status lookup by email hash",
        sql=(
            "SELECT status, locked, disabled, created_at "
            "FROM account "
            "WHERE email_hash = HMAC_SHA256(:email, :tenant_salt) "
            "LIMIT 1"
        ),
        param_names=["email", "tenant_salt"],
        facts_produced=["account_exists", "account_status", "is_locked", "is_disabled"],
    ),
    "login_attempt_counts": DbTemplate(
        template_id="login_attempt_counts",
        entity="login_attempt",
        description="Login attempt error distribution",
        sql=(
            "SELECT error_code, COUNT(*) as cnt "
            "FROM login_attempt "
            "WHERE service = :service "
            "AND created_at >= :since "
            "AND created_at < :until "
            "GROUP BY error_code "
            "ORDER BY cnt DESC "
            "LIMIT 20"
        ),
        param_names=["service", "since", "until"],
        facts_produced=["error_distribution", "total_failures", "top_error_code"],
    ),
}


def list_templates() -> list[DbTemplate]:
    return list(_TEMPLATES.values())


def _match_template(plan: MetabaseQueryPlan) -> DbTemplate | None:
    for tmpl in _TEMPLATES.values():
        if tmpl.entity != plan.entity:
            continue
        if any(f in tmpl.facts_produced for f in plan.facts_requested):
            return tmpl
    return None


# ---- Parameter resolution --------------------------------------------------

def _resolve_params(
    template: DbTemplate,
    plan_params: list[dict],
    evidence_session_id: str,
    sensitive_store: SensitiveValueStore,
) -> dict[str, str] | None:
    """Resolve template parameters from plan params; returns None on failure."""
    resolved: dict[str, str] = {}
    plan_param_map = {p["name"]: p for p in plan_params}

    for param_name in template.param_names:
        pp = plan_param_map.get(param_name)
        if pp is None:
            return None

        if pp.get("value_ref"):
            value = sensitive_store.resolve(evidence_session_id, pp["value_ref"])
            if value is None:
                return None
            resolved[param_name] = value
        elif "value" in pp:
            resolved[param_name] = str(pp["value"])
        else:
            return None

    return resolved


# ---- Connector -------------------------------------------------------------

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
        """Run a Metabase query via a registered template.

        Returns raw result rows (stored in raw store, never exposed to agent).
        """
        template = _match_template(plan)
        if template is None:
            raise ValueError(
                f"No registered template for entity={plan.entity}, facts={plan.facts_requested}"
            )

        resolved = _resolve_params(
            template, plan.params, evidence_session_id, self._sensitive_store
        )
        if resolved is None:
            raise ValueError("Failed to resolve template parameters")

        if self.is_live:
            rows = await self._execute_live(template, resolved)
        else:
            rows = self._fixture_rows(template)

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
    def _fixture_rows(template: DbTemplate) -> list[dict]:
        if template.entity == "account":
            return [{"status": "active", "locked": False, "disabled": False, "created_at": "2025-01-01"}]
        if template.entity == "login_attempt":
            return [
                {"error_code": "PHONE_NORMALIZATION_FAILED", "cnt": 42},
                {"error_code": "ACCOUNT_LOOKUP_FAILED", "cnt": 15},
            ]
        return [{"result": "fixture_data"}]
