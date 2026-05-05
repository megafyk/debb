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

**192 tests passing** (26 boundary tests) • **7 MCP tools** • **88 Python files**

---

## Changelog

### 2026-05-05

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
