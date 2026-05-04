from __future__ import annotations

from evidence_gate.connectors.metabase_template_registry import DbTemplate
from evidence_gate.sessions.sensitive_value_store import SensitiveValueStore


def resolve_params(
    template: DbTemplate,
    plan_params: list[dict],
    evidence_session_id: str,
    sensitive_store: SensitiveValueStore,
) -> dict[str, str] | None:
    """Resolve template parameters from plan params.

    Returns dict of param_name -> resolved_value, or None if resolution fails.
    """
    resolved: dict[str, str] = {}
    plan_param_map = {p["name"]: p for p in plan_params}

    for param_name in template.param_names:
        if param_name not in plan_param_map:
            return None
        pp = plan_param_map[param_name]

        if pp.get("value_ref"):
            value = sensitive_store.resolve(evidence_session_id, pp["value_ref"])
            if value is None:
                return None
            resolved[param_name] = value
        elif pp.get("source") == "connector_secret":
            resolved[param_name] = "__CONNECTOR_SECRET__"
        elif "value" in pp:
            resolved[param_name] = str(pp["value"])
        else:
            return None

    return resolved
