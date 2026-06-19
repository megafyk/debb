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

**255 tests passing** (28 boundary tests) • **7 MCP tools** • Metabase runs gated arbitrary SQL (no template registry)

---

## Changelog

### 2026-06-19

#### debug-repo: one combined code-review-graph per workspace (supersedes per-repo graphs)
**Context:** The debug-repo skill built a code-review-graph per registered repo:
each `register` ran `code-review-graph register/build/install --repo <path>`,
producing a `.code-review-graph/` DB *inside every service repo* and one CRG
multi-repo alias per repo (82 of them). The VDS services all live under one
workspace folder (`.../vds`, a Maven/IntelliJ aggregator over 125 repos), so the
per-repo model meant 82+ separate graph DBs and aliases for what is logically a
single workspace, and a full `build` ran on every single-repo `register`.

**Decision:** Build **one combined graph at the workspace root** (the common
parent of all registered repos) and decouple graph builds from registry writes:
- **register/update/delete are local-only** — they mutate `registry.json` and
  never call CRG. `register` no longer runs build/install; the per-repo
  `--no-graph-*` flags are removed.
- **New `setup-graph`** runs, at the workspace root: `install --repo <root>
  --platform claude-code -y`, `build --repo <root>`, then `register <root>
  --alias <root-name>` (register **last** — CRG rejects a path with no
  `.git`/`.code-review-graph`, which `build` creates). The root need not be a
  git repo (build/install walk the filesystem). Default build `--timeout` is 1800s.
- **New `migrate-graph --confirm`** is the one-time cutover: unregister every
  per-repo CRG alias under the root, delete each repo's stale
  `.code-review-graph/` dir, then `setup-graph`.
- The workspace root is derived as the single common parent of registered repo
  paths; mixed parents are rejected (`ambiguous_workspace_root`).

**Consequences:**
- Graph MCP tools resolve the whole workspace from one alias/DB; a single query
  spans all services — scope to one service by filtering on its `path` prefix.
- debug-jira's scan-time freshness contract now refreshes the combined graph at
  the root (`update --repo <root>`, `build` fallback), not per repo. The
  consumer-side debug-jira skill may need a matching follow-up.
- Adding/removing a repo no longer refreshes the graph automatically; run
  `setup-graph` to fold the change in.
- Repos outside the workspace root (e.g. this tool's own `debb` repo) keep their
  own per-repo graph and are left untouched by `migrate-graph`.

### 2026-06-11

#### Trust-boundary hardening audit (supersedes M7 Metabase template model)
**Context:** A full architecture/logic/security audit found that several gate
checks validated a *different representation* than what actually executed, and
that the at-rest layer didn't enforce the "raw data never leaks" premise. The
M7 ADR entry below still describes Metabase as *template-only execution (no
arbitrary SQL)* with a `TemplateRegistry` and an 8th `list_evidence_templates`
MCP tool — none of which exist anymore. The Metabase connector now executes the
agent's `sql_candidate` directly, gated only by `content_safety_checker`'s
regex denylist (7 MCP tools total).

**Decision:** Record the template→gated-SQL switch as the current architecture,
and close the validation-vs-execution gaps the switch opened:
- **Gate scans what executes.** `check_plan_safety` now validates `schema` is a
  bare SQL identifier and re-runs the SQL denylist against the
  `{schema}`-substituted SQL, not just the pre-substitution `sql_candidate`
  (previously an agent could route `UNION SELECT`/`DROP` through `schema`).
- **Quickwit filter field names** are restricted to an identifier shape in
  `schema_checker` so a crafted `field` can't inject top-level Lucene and widen
  the query past the validated filters.
- **Leakage patterns** in `redaction/leakage.py` (used by both plan-safety and
  report-review) are brought back in sync with the redactor: VN MSISDN forms
  (`84…`, `0…`) and `token:` assignments are no longer accepted.
- **Connector trust boundary:** Metabase query failures (2xx body with
  `status:"failed"`) now raise instead of being reported as an empty success;
  the Metabase session token is cached and refreshed on 401; the blocking Jira
  fetch runs off the event loop.
- **At-rest:** `SensitiveValueStore`/`RawEvidenceStore` create dirs `0700` and
  files `0600`; `redact_value` redacts dict keys (PII used as a map key);
  caller-supplied `trace_id` is validated before it becomes a folder name
  (path-traversal fix).
- **Bounds:** mixed naive/aware `from`/`to` no longer crash the bounds check
  (naive treated as UTC); Metabase results are capped to `MAX_METABASE_ROWS`
  (mirroring Quickwit's `max_hits`), recorded as a truncation in the execution
  log; Quickwit refuses to fall back to a match-all `*` when every filter
  resolves to nothing.

**Consequences:**
- 255 tests passing (added `test_audit_fixes.py`, 24 regression tests).
- `debugging_system_implementation_plan.md` §10's `list_evidence_templates` /
  `TemplateRegistry` design is superseded by this entry; the live system has 7
  MCP tools and no template registry.
- The regex SQL denylist remains a weaker control than an allowlist of approved
  templates; it is now at least applied to the executed SQL. A future ADR could
  reintroduce a template/allowlist model if arbitrary SQL proves too permissive.

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
