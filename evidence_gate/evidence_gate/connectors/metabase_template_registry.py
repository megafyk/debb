from __future__ import annotations

from dataclasses import dataclass, field

from evidence_gate.contracts.query_plan import MetabaseQueryPlan


@dataclass
class DbTemplate:
    template_id: str
    entity: str
    description: str
    sql: str
    param_names: list[str]
    facts_produced: list[str] = field(default_factory=list)


class TemplateRegistry:
    def __init__(self) -> None:
        self._templates: dict[str, DbTemplate] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        self._templates["account_status_by_phone_hash"] = DbTemplate(
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
        )
        self._templates["account_status_by_email_hash"] = DbTemplate(
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
        )
        self._templates["login_attempt_counts"] = DbTemplate(
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
        )

    def match(self, plan: MetabaseQueryPlan) -> DbTemplate | None:
        for tmpl in self._templates.values():
            if tmpl.entity != plan.entity:
                continue
            if any(f in tmpl.facts_produced for f in plan.facts_requested):
                return tmpl
        return None

    def get(self, template_id: str) -> DbTemplate | None:
        return self._templates.get(template_id)
