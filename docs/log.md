# Project Log

Tracks changes and implementation progress for the AI-assisted production debugging system.

---

## Milestone Status

| # | Milestone | Status |
|---|---|---|
| M1 | Skill skeleton | ✅ Done |
| M2 | evidence_gate core (sessions, sanitized Jira fixtures) | ✅ Done |
| M3 | Real Jira ingestion | ✅ Done |
| M4 | Service repo map & code scan | ✅ Done |
| M5 | Query plan validation (state machine) | ✅ Done |
| M6 | Quickwit masked log loop | ✅ Done |
| M7 | Metabase templates | ✅ Done |
| M8 | Reports and evals | ✅ Done |

**175 tests passing** (26 boundary tests) • **8 MCP tools** • **65 Python files** (34 source + 31 tests)

---

## Changelog

### 2026-05-08

#### Quickwit logs now flow through Grafana `/ds/query`
**Context:** The Quickwit connector previously called Quickwit's native
search API (`/api/v1/{index}/search`). Production reads now go through
Grafana, which proxies to Quickwit as a registered data source.

**Decision:** Reshape `QuickwitQueryPlan` to mirror Grafana's
`MetricRequest` at the wire boundary while keeping plan-level helpers
(`filters`, `fields_requested`, `query_intent`, `max_hits`):
- `index_hint` → `datasource_uid` (Grafana data source UID)
- `time_window{start,end}` → top-level `from`/`to` (ISO 8601, epoch ms,
  or Grafana relative like `now-1h`)
- Added `ref_id`, `max_data_points`, `interval_ms` for the per-query slot
- Connector posts to `<quickwit_url>/api/ds/query` with
  `{from, to, queries:[{refId, datasource:{uid}, query:<Lucene>,
  format:"logs", ...}]}` and parses
  `QueryDataResponse.results[refId].frames` into row dicts
- Bounds checker still narrows ISO `from`/`to` over 24h; epoch ms /
  relative strings pass through unchanged

**Replan signal:** Connector now returns
`QuickwitQueryResult{hits, is_valuable, reason}`. `is_valuable=False`
(`reason="zero_hits"`) tells the planning agent to revise the plan and
resubmit; the `debug-jira` skill prompt caps replans at 3 attempts.

**Consequences:**
- Existing `quickwit_url`/`quickwit_username`/`quickwit_password` env
  vars now point at Grafana with basic auth — variable names misleading,
  no rename in this change.
- Per-`queries[i]` body uses a reasonable Quickwit-Grafana-plugin shape
  (`query`/`datasource`/`format='logs'`); revisit when the plugin's
  exact field names are confirmed against a working Grafana panel.
- Skill-prompt change: planner picks `fields_requested` from the
  sanitized Jira ticket plus log statements grepped in the mapped
  service repo — no guessing.
- 198 tests passing (added 2 in `test_contracts.py`).

### 2026-05-05

#### Directory consolidation
Flattened the per-plan §9 layout into fewer modules where each directory
held only 1–2 files or single-call-site helpers:
- Dropped `app/`: `config.py` and `main.py` hoisted to package root
- Dropped `audit/`: `audit_logger.py` (18 lines) hoisted to root
- Dropped `sessions/`: `evidence_session_store` and `sensitive_value_store`
  merged into `storage/` (they were storage)
- Dropped `contracts/` (7 files): merged into a single `contracts.py` at
  package root
- Merged Metabase helpers (`metabase_api_spec_loader`,
  `metabase_param_resolver`, `metabase_template_registry`) into
  `metabase_connector.py` — each had exactly one call site
- Merged `jira_field_mapper.py` into `jira_connector.py` — same single
  producer / single consumer
- Removed corresponding helper-only unit tests (3 files); integration
  tests in `test_metabase_connector.py` / `test_metabase_executor.py`
  still cover behavior

Result: 88 → 65 Python files, 11 → 6 source directories. All 175 tests
green; end-to-end flow + boundary tests unchanged.

#### Plan-conformance audit + simplification pass
- Fixed bounds-narrowing bug: `bounds_checker` produced an `adjusted_plan`
  but `request_pipeline` only logged narrowing strings; the executor still
  ran the original over-broad plan. Now the narrowed plan is persisted on
  the request via `EvidenceRequestStore.transition` (audit log excludes
  the verbose plan body)
- Added `list_evidence_templates` MCP tool (plan §10) backed by
  `TemplateRegistry.list_all`; documented in Skill reference but was
  unregistered (8 MCP tools total)
- Made `MetabaseApiSpecLoader` actually guard: `MetabaseConnector.__init__`
  now fails fast if `/api/session` or `/api/dataset` aren't in the spec
- Metabase `bounds_checker` now returns the truncated plan when
  `facts_requested > 20` (was cosmetic before)
- Consolidated duplicated PII/credential regex tuples + recursive walker
  from `content_safety_checker` and `report_reviewer` into shared
  `redaction/leakage.py` (~40 lines saved)
- Removed dead code: `metabase_fixture_session_header`, unused `UTC` /
  `SensitiveRef` imports, unused `_ALLOWED_FIELDS` set in
  `jira_field_mapper`
- New tests: persisted-plan narrowing, `list_evidence_templates`

#### Post-milestone polish
- Added `test_sensitive_features_without_raw_values.py` (4 boundary tests per §23)
- Added `test_no_raw_db_to_agent.py` boundary test
- Replaced placeholder `quickwit_api.json` with real Quickwit search API spec
- Added `make lint` target to Makefile
- Fixed SELECT * regex in content_safety_checker
- All 192 tests passing (26 boundary tests)

#### M8 — Reports and evals
- Created `DebugReport` contract model
- Created `report_reviewer.py` — programmatic PII/credential/overstatement checker
- Added `submit_debug_report` MCP tool (7 tools total)
- Added full end-to-end flow eval test

#### M7 — Metabase templates
- Created `metabase_connector.py` — template-only execution (no arbitrary SQL)
- Created `metabase_template_registry.py` — 3 approved SQL templates
- Created `metabase_param_resolver.py` — resolves SECURE_VALUE_REFs
- Created `metabase_api_spec_loader.py` — validates endpoints against OpenAPI spec
- Created `db_redactor.py` — row redaction + diagnostic feature extraction
- Wired `create_metabase_evidence_request` MCP tool

#### M6 — Quickwit masked log loop
- Created `quickwit_connector.py` — async search with sensitive ref resolution
- Created `raw_evidence_store.py` — internal-only raw hit storage
- Created `log_redactor.py` — field-scoped PII redaction + masked package builder
- Created `masked_package_store.py` — Pydantic-native persistence
- Created `evidence_executor.py` — full state-machine execution pipeline
- Wired `create_quickwit_evidence_request` and `get_masked_evidence_package` MCP tools

#### M5 — Query plan validation
- Created `schema_checker.py`, `content_safety_checker.py`, `bounds_checker.py`
- Created `request_pipeline.py` — validates plans through schema→safety→bounds
- Created `evidence_request_store.py` — state machine for request lifecycle
- Added `get_evidence_request_status` MCP tool

#### M4 — Service repo map & code scan
- Schemas and templates in skill skeleton
- Added `.code-review-graphignore`

#### M3 — Real Jira ingestion
- Created `jira_connector.py` — dual-mode (live/fixture) with httpx
- Created `jira_field_mapper.py` — maps raw Jira fields to SanitizedTicketContext
- Created `pii_extractor.py` — regex-based PII detection with deduplication
- Updated `jira_redactor.py` — two-pass redaction with sensitive ref storage

#### M2 — evidence_gate core
- Created `contracts/` — Pydantic models for all domain objects
- Created `sessions/` — evidence session store + sensitive value store
- Created `storage/` — JSON/JSONL persistence layer
- Created `audit/` — append-only audit logger
- Created `mcp_server/` — FastMCP stdio server with `start_debugging_session` and `get_sanitized_jira_ticket` tools
- Created initial test suite (38 tests)

#### M1 — Skill skeleton
- Created `.claude/skills/debug-jira/SKILL.md` — workflow definition + safety rules
- Created 7 schemas, 7 prompts, 2 templates, 5 references
- Established project structure: pyproject.toml, Makefile, .env.example
