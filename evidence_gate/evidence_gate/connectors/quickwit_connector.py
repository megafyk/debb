from __future__ import annotations

from datetime import datetime

import httpx

from evidence_gate.config import Settings
from evidence_gate.audit_logger import AuditLogger
from evidence_gate.connectors.auth import quickwit_basic_auth_header
from evidence_gate.contracts import QuickwitQueryPlan, QuickwitQueryResult
from evidence_gate.storage.sensitive_value_store import SensitiveValueStore


class QuickwitConnector:
    _PLUGIN_ID = "quickwit-quickwit-datasource"

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
        return self._settings.quickwit_enabled and bool(self._settings.quickwit_url)

    async def execute(
        self, plan: QuickwitQueryPlan, evidence_session_id: str
    ) -> QuickwitQueryResult:
        body = self._build_search_body(plan, evidence_session_id)

        if self.is_live:
            url = f"{self._settings.quickwit_url}/api/ds/query"
            headers = quickwit_basic_auth_header(self._settings)
            headers["x-plugin-id"] = self._PLUGIN_ID
            headers["x-datasource-uid"] = plan.datasource_uid
            if self._settings.quickwit_org_id > 0:
                headers["X-Grafana-Org-Id"] = str(self._settings.quickwit_org_id)
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json=body, headers=headers)
                resp.raise_for_status()
                hits = self._parse_grafana_response(resp.json(), plan.ref_id)
        else:
            hits = self._fixture_hits(plan.fields_requested)

        is_valuable = len(hits) > 0
        reason = "" if is_valuable else "zero_hits"

        self._audit.log(
            evidence_session_id,
            "quickwit_query_executed",
            {
                "datasource_uid": plan.datasource_uid,
                "hit_count": len(hits),
                "is_valuable": is_valuable,
            },
        )
        return QuickwitQueryResult(hits=hits, is_valuable=is_valuable, reason=reason)

    def _build_search_body(
        self, plan: QuickwitQueryPlan, evidence_session_id: str
    ) -> dict:
        terms: list[str] = []
        for f in plan.filters:
            field = _lucene_field(f.field)
            if f.op == "matches_sensitive_ref" and f.value_ref:
                resolved = self._sensitive_store.resolve(
                    evidence_session_id, f.value_ref
                )
                if resolved:
                    terms.append(f"{field}:{_lucene_literal(resolved)}")
            elif f.op == "=" and f.value is not None:
                terms.append(f"{field}:{_lucene_literal(f.value)}")
            elif f.op == "in" and isinstance(f.value, list):
                # Repeat the field name per OR clause: `(level:"A" OR level:"B")`.
                # Quickwit's Tantivy parser rejects the grouped form
                # `level:("A" OR "B")` with "failed to parse query".
                parts = [f"{field}:{_lucene_literal(v)}" for v in f.value]
                terms.append("(" + " OR ".join(parts) + ")")
            elif f.op == "contains" and f.value is not None:
                terms.append(_lucene_contains(field, f.value))

        query = " AND ".join(terms) if terms else "*"

        sub_query = {
            "refId": plan.ref_id,
            "datasource": {"type": self._PLUGIN_ID, "uid": plan.datasource_uid},
            "query": query,
            "alias": "",
            "metrics": [
                {
                    "type": "logs",
                    "id": "1",
                    "settings": {
                        "limit": str(plan.max_hits),
                        "sortDirection": "desc",
                    },
                }
            ],
            "bucketAggs": [],
            "timeField": "",
            "intervalMs": plan.interval_ms,
            "maxDataPoints": plan.max_data_points,
        }

        return {
            "from": _to_grafana_time(plan.from_),
            "to": _to_grafana_time(plan.to),
            "queries": [sub_query],
        }

    @staticmethod
    def _parse_grafana_response(payload: dict, ref_id: str) -> list[dict]:
        # Grafana QueryDataResponse: {"results": {"<refId>": {"frames": [...]}}}.
        # Each frame has schema.fields[*].name + data.values (column-major).
        # Zip columns into row dicts; tolerate missing pieces by returning [].
        results = payload.get("results", {})
        ref_block = results.get(ref_id) or next(iter(results.values()), {})
        frames = ref_block.get("frames", []) if isinstance(ref_block, dict) else []
        rows: list[dict] = []
        for frame in frames:
            fields = (frame.get("schema") or {}).get("fields") or []
            values = (frame.get("data") or {}).get("values") or []
            if not fields or not values:
                continue
            names = [f.get("name", f"col_{i}") for i, f in enumerate(fields)]
            row_count = min(len(col) for col in values) if values else 0
            for i in range(row_count):
                rows.append({names[c]: values[c][i] for c in range(len(names))})
        return rows

    @staticmethod
    def _fixture_hits(fields_requested: list[str]) -> list[dict]:
        hits: list[dict] = []
        for i in range(1, 4):
            hit = {field: f"fixture_{field}_{i}" for field in fields_requested}
            hits.append(hit)
        return hits


def _to_grafana_time(value: str) -> str:
    # Grafana accepts epoch ms, ISO 8601, or relative strings (now-1h).
    # Convert ISO to epoch ms; pass through everything else unchanged.
    try:
        dt = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return value
    return str(int(dt.timestamp() * 1000))


def _lucene_literal(value: object) -> str:
    # Quote string filter values so Lucene treats them as a single phrase.
    # Without this, values with whitespace or hyphens get split into separate
    # terms and the query fails (Quickwit rejects e.g. `timestamp:send`).
    if not isinstance(value, str):
        return str(value)
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _lucene_field(name: str) -> str:
    # Escape `/` inside Lucene field names. Without this,
    # `kubernetes.labels.app_kubernetes_io/instance:"x"` is rejected — the
    # slash is a reserved regex delimiter in Lucene's query parser.
    return name.replace("/", "\\/")


def _lucene_contains(field: str, value: object) -> str:
    # `contains` is engineer-level "this literal appears in the field".
    # A multi-word value as a phrase query (`field:"a b c"`) requires the
    # tokens to appear in order and depends on positions being indexed —
    # Quickwit rejects phrase queries on fields whose analyzer does not
    # index positions. AND-of-tokens is the closer "contains" semantic
    # and works on plain tokenized fields.
    if isinstance(value, str) and len(value.split()) > 1:
        parts = [f"{field}:{_lucene_literal(tok)}" for tok in value.split()]
        return "(" + " AND ".join(parts) + ")"
    return f"{field}:{_lucene_literal(value)}"
