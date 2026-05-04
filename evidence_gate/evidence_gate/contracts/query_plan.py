from __future__ import annotations

from pydantic import BaseModel, Field


class QueryFilter(BaseModel):
    field: str
    op: str  # =, !=, in, not_in, contains, matches_sensitive_ref
    value: str | list[str] | None = None
    value_ref: str | None = None


class TimeWindow(BaseModel):
    start: str
    end: str


class QuickwitQueryPlan(BaseModel):
    type: str = "quickwit_query_plan"
    evidence_session_id: str
    service: str
    repository: str = ""
    code_paths: list[str] = []
    index_hint: str
    time_window: TimeWindow
    query_intent: str
    filters: list[QueryFilter]
    fields_requested: list[str]
    max_hits: int = Field(default=100, ge=1, le=1000)
    output_profile: str = ""


class MetabaseQueryPlan(BaseModel):
    type: str = "metabase_query_plan"
    evidence_session_id: str
    service: str
    repository: str = ""
    code_paths: list[str] = []
    entity: str
    query_intent: str
    sql_candidate: str = ""
    params: list[dict] = []
    facts_requested: list[str]
    output_profile: str = ""
