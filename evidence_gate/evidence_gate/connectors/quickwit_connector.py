from __future__ import annotations

from datetime import UTC, datetime

import httpx

from evidence_gate.app.config import Settings
from evidence_gate.audit.audit_logger import AuditLogger
from evidence_gate.connectors.auth import quickwit_basic_auth_header
from evidence_gate.contracts.query_plan import QuickwitQueryPlan
from evidence_gate.sessions.sensitive_value_store import SensitiveValueStore


class QuickwitConnector:
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
        return bool(self._settings.quickwit_url)

    async def execute(
        self, plan: QuickwitQueryPlan, evidence_session_id: str
    ) -> list[dict]:
        body = self._build_search_body(plan, evidence_session_id)

        if self.is_live:
            url = f"{self._settings.quickwit_url}/api/v1/{plan.index_hint}/search"
            headers = quickwit_basic_auth_header(self._settings)
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=body, headers=headers)
                resp.raise_for_status()
                hits = resp.json().get("hits", [])
        else:
            hits = self._fixture_hits(plan.fields_requested)

        self._audit.log(
            evidence_session_id,
            "quickwit_query_executed",
            {"index": plan.index_hint, "hit_count": len(hits)},
        )
        return hits

    def _build_search_body(
        self, plan: QuickwitQueryPlan, evidence_session_id: str
    ) -> dict:
        terms: list[str] = []
        for f in plan.filters:
            if f.op == "matches_sensitive_ref" and f.value_ref:
                resolved = self._sensitive_store.resolve(
                    evidence_session_id, f.value_ref
                )
                if resolved:
                    terms.append(f"{f.field}:{resolved}")
            elif f.op == "=" and f.value is not None:
                terms.append(f"{f.field}:{f.value}")
            elif f.op == "in" and isinstance(f.value, list):
                joined = " ".join(f.value)
                terms.append(f"{f.field}:IN [{joined}]")
            elif f.op == "contains" and f.value is not None:
                terms.append(f"{f.field}:{f.value}")

        start_epoch = int(
            datetime.fromisoformat(plan.time_window.start).timestamp()
        )
        end_epoch = int(
            datetime.fromisoformat(plan.time_window.end).timestamp()
        )

        return {
            "query": " AND ".join(terms) if terms else "*",
            "max_hits": plan.max_hits,
            "start_timestamp": start_epoch,
            "end_timestamp": end_epoch,
            "search_fields": plan.fields_requested,
        }

    @staticmethod
    def _fixture_hits(fields_requested: list[str]) -> list[dict]:
        hits: list[dict] = []
        for i in range(1, 4):
            hit = {field: f"fixture_{field}_{i}" for field in fields_requested}
            hits.append(hit)
        return hits
