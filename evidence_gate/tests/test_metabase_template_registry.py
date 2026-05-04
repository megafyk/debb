from __future__ import annotations

from evidence_gate.connectors.metabase_template_registry import DbTemplate, TemplateRegistry
from evidence_gate.contracts.query_plan import MetabaseQueryPlan


def _make_plan(**overrides) -> MetabaseQueryPlan:
    defaults = dict(
        type="metabase_query_plan",
        evidence_session_id="ESESS-1",
        service="login-service",
        entity="account",
        query_intent="Check account status",
        facts_requested=["account_exists", "account_status"],
        params=[],
    )
    defaults.update(overrides)
    return MetabaseQueryPlan(**defaults)


def test_registry_has_builtins():
    reg = TemplateRegistry()
    assert reg.get("account_status_by_phone_hash") is not None
    assert reg.get("account_status_by_email_hash") is not None
    assert reg.get("login_attempt_counts") is not None


def test_match_account_entity():
    reg = TemplateRegistry()
    plan = _make_plan(entity="account", facts_requested=["account_exists"])
    tmpl = reg.match(plan)
    assert tmpl is not None
    assert tmpl.entity == "account"


def test_match_login_attempt_entity():
    reg = TemplateRegistry()
    plan = _make_plan(entity="login_attempt", facts_requested=["error_distribution"])
    tmpl = reg.match(plan)
    assert tmpl is not None
    assert tmpl.template_id == "login_attempt_counts"


def test_match_returns_none_for_unknown_entity():
    reg = TemplateRegistry()
    plan = _make_plan(entity="unknown_table", facts_requested=["something"])
    assert reg.match(plan) is None


def test_match_returns_none_for_unmatched_facts():
    reg = TemplateRegistry()
    plan = _make_plan(entity="account", facts_requested=["something_unrelated"])
    assert reg.match(plan) is None


def test_get_nonexistent_template():
    reg = TemplateRegistry()
    assert reg.get("nonexistent") is None


def test_template_param_names():
    reg = TemplateRegistry()
    tmpl = reg.get("login_attempt_counts")
    assert set(tmpl.param_names) == {"service", "since", "until"}
