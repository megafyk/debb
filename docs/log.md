# Project Log

Tracks changes and implementation progress for the AI-assisted production debugging system.
Add a new entry under **Changelog** for every meaningful change. Update **Milestone Status** when a milestone moves forward.

---

## Milestone Status

| # | Milestone | Status | Progress |
|---|---|---|---|
| 1A | debugging_pilot ticket intake & trace context | 🔶 In progress | ~80% |
| 1B | evidence_gate sanitized Jira fixture path | ✅ Done | ~95% |
| 1C | Real Jira REST ingestion | ✅ Done | ~90% |
| 1D | Deterministic evidence planning | ✅ Done | ~90% |
| 1E | AI planning behind typed output | 🔶 In progress | ~50% |
| 2 | evidence_gate registry, state machine, deterministic services | 🔶 In progress | ~80% |
| 3 | Quickwit/Kibana log connector | ✅ Done | ~90% |
| 4 | Leak-prevention and boundary tests | ✅ Done | ~90% |
| 5 | Request diagnostics API/CLI | 🔶 In progress | ~65% |
| 6 | Metabase aggregate templates | 🔶 In progress | ~70% |
| 7 | Production hardening and evals | 🔶 In progress | ~40% |

---

## Known Gaps

### Critical (must complete before connecting to real production data)
- [x] **M4 boundary tests** — `tests/boundary/` created with 21 tests; passes DebPilotLeakageSentinel and SafetyScanner
- [x] **M1C real Jira connector** — `RealJiraConnector` implemented with Basic Auth, `JIRA_ENABLED` opt-in flag, respx-tested
- [ ] **Presidio / PII detector** — `redaction/pii_detector.py` not implemented; `RedactionGateway` has no real PII recognizer
- [ ] **Formal state machine** — `StateTransitionStore` absent; transitions logged to audit but not tracked as first-class objects

### Important
- [ ] `reasoning/` module not started (hypothesis_engine, ranker, contradiction_checker, confidence_calculator)
- [ ] `retrieval/code_retriever.py` and `wiki_retriever.py` not started
- [ ] Real model-backed agents (all agents are deterministic stubs)
- [ ] `evidence_gate requests list/show/explain` CLI commands missing (only `decisions` exists)
- [x] `deterministic_services/rules/logs.yaml` and `rules/database.yaml` rule files — created with rule_loader.py
- [ ] `StateTransitionStore` as a dedicated store

### Nice to have
- [ ] OpenTelemetry SDK integration (trace IDs carried as contract fields only)
- [ ] `jira_basic_auth_provider.py`, `jira_field_mapper.py`, `jira_redactor.py`, `jira_ticket_normalizer.py`
- [ ] `kibana_connector.py`
- [ ] Additional log templates: `stack_hash_by_version_v1`, `trace_lookup_v1`
- [ ] Additional DB templates: `phone_normalization_debug_summary_v1`, `customer_name_unicode_debug_summary_v1`, `email_canonicalization_debug_summary_v1`, `order_failure_aggregate_v1`, `payment_error_distribution_v1`
- [ ] `sensitive_values/sensitive_value_ref_store.py`, `parameter_resolver.py`, `token_service.py`
- [ ] `DiagnosticFeatureExtractor` for phone/name diagnostic masking
- [ ] `docs/jira_rest_api.yaml` (currently only `jira_swagger.v3.json`) and `docs/jira_ticket_ingestion.md`
- [ ] `context/masked_evidence_context_builder.py`, `citation_builder.py`, `context_budget.py`
- [ ] `reporting/markdown_renderer.py`, `report_reviewer.py`
- [ ] `api/debug_sessions.py`, `api/jira_ticket_intake.py` (routes currently inline in `main.py`)
- [ ] `api/jira_ingestion.py` in evidence_gate (FastAPI route for `/jira/tickets/{id}/sanitized`)

---

## Changelog

### 2026-05-03 (continued)

#### M3 + M11.8 — Real Quickwit HTTP connector + 5 missing DB templates

**Real Quickwit connector** (`evidence_gate/connectors/real_quickwit_connector.py`):
- `RealQuickwitConnector` uses `httpx` + Basic Auth; maps `BoundedLogQuery` to Quickwit `POST /api/v1/{index_id}/search`
- `_filters_to_query()` converts `filters` dict to Quickwit query string; `limit` key excluded
- Field projection applied client-side from `query.fields` allowlist
- `EVIDENCE_GATE_QUICKWIT_ENABLED=false` opt-in guard — prevents stub credentials hitting real server in tests
- `_default_log_connector(settings)` factory auto-selects real vs stub; `connectors/__init__.py` exports `RealQuickwitConnector`
- 13 new tests with respx mocks (Basic Auth header, field projection, timestamp format, HTTP errors)

**Test isolation fix** (`conftest.py` at project root):
- Added root `conftest.py` that sets `EVIDENCE_GATE_JIRA_ENABLED=false` and `EVIDENCE_GATE_QUICKWIT_ENABLED=false` via `os.environ.setdefault` before any `Settings()` instantiation
- Fixes 8 tests that were hitting the real Jira server when `.env` had `JIRA_ENABLED=true`

**5 missing DB templates** in `evidence_gate/templates/db_templates/`:
- `phone_normalization_debug_summary_v1.yaml` — phone format validation debug
- `customer_name_unicode_debug_summary_v1.yaml` — Unicode normalization debug
- `email_canonicalization_debug_summary_v1.yaml` — email canonicalization debug
- `order_failure_aggregate_v1.yaml` — aggregated order failure analysis
- `payment_error_distribution_v1.yaml` — payment error code distribution (e.g. CORE_MC_TB_00003)

All templates use pseudonymised/sensitive_identifier_ref params — no raw PII in output fields.

**Config change**: `quickwit_enabled: bool = Field(default=False)` added to `Settings`.

**Test count**: 92 tests, all passing.



#### M4 Boundary tests implemented (21 new tests)
- Created `tests/boundary/` at repo root; added to `pyproject.toml` testpaths.
- `test_no_raw_jira_to_debugging_pilot.py` (6 tests): PoisonedJiraConnector fixture; asserts SanitizedTicketContext, REST API response, EvidencePlatformClient output, and disk storage are all clean.
- `test_no_raw_logs_to_debugging_pilot.py` (5 tests): PoisonedLogConnector with Bearer token, email, request_body, raw stack traces; asserts MaskedEvidencePackage passes DebPilotLeakageSentinel + SafetyScanner and secrets are filtered before clustering.
- `test_no_raw_db_rows_to_debugging_pilot.py` (4 tests): PoisonedDbConnector returning rows with raw phone/email; asserts account_internal_id is HMAC-tokenized, not raw, in the masked package.
- `test_no_credentials_in_traces_or_audit.py` (6 tests): Fake Jira/Quickwit credentials; asserts they don't appear in audit events, SIEM export, stored files, or SanitizedTicketContext metadata.
- **Real bug fixed**: `JiraIngestionService._sanitize_text` was missing `Authorization: Bearer` and `Cookie:` header redaction patterns — added `[REDACTED_HEADER]` and `[REDACTED_BEARER]` patterns.

#### M1C Real Jira connector implemented
- Added `httpx` to `evidence-gate` package dependencies.
- Created `evidence_gate/connectors/real_jira_connector.py` (`RealJiraConnector`): HTTP Basic Auth from Settings, explicit field allowlist (`JIRA_ALLOWED_FIELDS`), paginated comment fetch, graceful fallback on comment 403/4xx.
- Added `EVIDENCE_GATE_JIRA_ENABLED=false` flag to Settings (opt-in guard so placeholder `.env` credentials don't trigger real HTTP calls in tests).
- Updated `JiraIngestionService._default_jira_connector()` to use `RealJiraConnector` only when `jira_enabled=True` and both credentials are set.
- 6 new tests in `evidence_gate/tests/test_real_jira_connector.py` using `respx` mocks.

#### Deterministic rule YAML files created
- `evidence_gate/deterministic_services/rules/logs.yaml`: max_window_minutes=180, default_limit=500, max_limit=1000, blocked_fields (10 fields), allowed_fields (14 fields), required_filters, redaction config.
- `evidence_gate/deterministic_services/rules/database.yaml`: registered_templates, blocked_columns (14 columns), enforcement flags (no_arbitrary_sql, no_select_star, require_registered_template, etc.), redaction config.
- Created `evidence_gate/deterministic_services/rule_loader.py`: typed `LogRules` + `DatabaseRules` Pydantic models; `load_log_rules()` / `load_database_rules()` with hardcoded fallback defaults.
- Wired rule YAML into `RequestContentSafetyChecker` (blocked_fields from YAML) and `RequestBoundsChecker` (max_log_window_minutes from YAML).


- Updated `docs/debugging_system_implementation_plan.md` section 1.4 and 11.4 with concrete Jira Cloud REST API details from `docs/jira_api.json` (OpenAPI 3.0.1):
  - Explicit endpoints: `GET /rest/api/2/issue/{issueIdOrKey}`, paginated `GET .../comment`, `GET .../changelog`
  - Auth: HTTP Basic with `EVIDENCE_GATE_JIRA_USERNAME` (email) + `EVIDENCE_GATE_JIRA_PASSWORD` (API token)
  - Allowed field list for `fields=` param (explicit allowlist, never `*all`)
  - Full field-to-`SanitizedTicketContext` mapping table
  - Blocked fields list
- Updated section 11.8 (Quickwit connector) with Quickwit REST API endpoint shape from official docs.
- Flagged that `docs/quickwit_api.json` currently contains the **Grafana HTTP API** spec, not Quickwit. Action required: replace with real Quickwit OpenAPI spec from `GET http://{host}:7280/openapi.json` or Quickwit GitHub.



#### Environment setup
- Added `python-dotenv==1.2.2` to `debugging-pilot` and `evidence-gate` packages via `uv add`.
- Added `load_dotenv()` at the top of all four entry points: `debugging_pilot/app/main.py`, `debugging_pilot/cli.py`, `evidence_gate/app/main.py`, `evidence_gate/cli.py`.
- Expanded `debugging_pilot/app/config.py` (`DEB_PILOT_` prefix):
  - `DEB_PILOT_DATA_DIR` — local JSON store path (default: `debugging_pilot/.data`)
  - `DEB_PILOT_EVIDENCE_GATE_URL` — evidence_gate service URL (default: `http://localhost:8002`)
- Expanded `evidence_gate/app/config.py` (`EVIDENCE_GATE_` prefix):
  - `EVIDENCE_GATE_DATA_DIR` — local JSON store path
  - `EVIDENCE_GATE_JIRA_BASE_URL/USERNAME/PASSWORD` — Jira REST Basic Auth
  - `EVIDENCE_GATE_QUICKWIT_URL/API_KEY` — Quickwit connector
  - `EVIDENCE_GATE_METABASE_URL/API_KEY` — Metabase connector
  - `EVIDENCE_GATE_HMAC_SALT` — tokenizer salt
- Updated `HmacTokenizer` to read salt from `Settings()` instead of a hardcoded default.
- Created `.env.example` with all variables documented.
- Added `.env` and `debugging_pilot/.data/` to `.gitignore`.

#### Platform setup
- Installed `code-review-graph` for Codex and Claude Code platforms only.
  - Configured MCP in `~/.codex/config.toml` and `.mcp.json`.
  - Installed Claude Code hooks in `.claude/settings.json` and `.git/hooks/pre-commit`.
  - Built knowledge graph: 96 files, 439 nodes, 2,219 edges.
- Removed other platform config files: `.cursorrules`, `.windsurfrules`, `.kiro/`, `.opencode.json`, `GEMINI.md`.

#### Documentation
- Rewrote `README.md` with full "how to use" guide: prerequisites, installation, architecture diagram, end-to-end workflow (5 steps), CLI reference, API endpoint tables, data directory config, and current limitations.
- Copied `AGENTS.md` content to `CLAUDE.md` and `GEMINI.md` (GEMINI.md later removed).

---

### 2026-05-02 (initial state — reconstructed from codebase)

#### debugging-contracts
- `DebugSession`, `SanitizedTicketContext`, `EvidenceRequest`, `EvidenceRequestDecision`, `MaskedEvidencePackage`, `MaskedEvidenceItem`, `AuditReference`, `DebugReport`, `Hypothesis`, `EvidenceSource` enum, `EvidenceRequestStatus` enum, validators blocking raw SQL / `SELECT *` / missing service / missing entity / raw PII.
- Contract compatibility tests and schema version defaults.

#### debugging_pilot
- FastAPI app with `/healthz`, `/debug-sessions`, `/evidence-plans`, `/reports` endpoints.
- `DebugSessionStore` with idempotent replay via trace ID.
- `TicketReferenceParser` for Jira issue keys and URLs.
- `EvidencePlanBuilder` — deterministic planning pipeline.
- `RequestQualityChecker`.
- `TriageAgent`, `EvidencePlanningAgent` (deterministic stubs).
- `ReportGenerator`.
- `EvidencePlatformClient` HTTP client for evidence_gate.
- `leakage_sentinel.py` in context module.
- Historical eval cases: `auth_login_failure.json`, `checkout_error_cluster.json`.
- `HistoricalEvidencePlanEval`, `ReportQualityEval`.
- `debugging-pilot` CLI: stdin → evidence plan JSON; `eval-historical` subcommand.

#### evidence_gate
- FastAPI app with full evidence request, approval, audit, retention, metrics, and template APIs.
- `EvidenceRequestWorkflow`, `ConnectorExecutionWorkflow`.
- `JsonFileStore`, `RawEvidenceStore`.
- `EvidenceRequestStore`, `IdempotencyStore`, `AuditEventStore`, `MaskedPackageStore`, `OutcomeStore`, `DecisionStore`.
- Named deterministic services: `RequestSchemaChecker`, `RequestContentSafetyChecker`, `RequestBoundsChecker`, `TemplateMatcher`, `ConnectorJobBuilder`, `OutputProfileChecker`.
- `PolicyEngine` (auto approve/narrow/reject).
- `LogTemplateRegistry` + `error_cluster_by_service_v1.yaml`.
- `DbTemplateRegistry` + `account_debug_summary_by_phone_v1.yaml`.
- `LogQueryBuilder`, `DbQueryBuilder`.
- `QuickwitConnector`, `MetabaseConnector` (stubs).
- `JiraConnector` protocol + `StubJiraConnector`; `JiraRestSpecLoader`; `JiraIngestionService`.
- `RedactionGateway`, `LogRedactor`, `DbRedactor`, `SecretScanner`, `HmacTokenizer`.
- `AuditExporter`, `SiemExporter`, `RetentionCleanupJob`.
- `MetricsCollector` + platform metrics snapshot API.
- `DiagnosticsService`, masked package preview.
- Scope diff API (`workflow.get_scope_diff`).
- `get_sanitized_jira_ticket` MCP tool (backed by `JiraIngestionService` + stub connector).
- FastMCP server with 5 tools: `create_evidence_request`, `get_evidence_request_status`, `get_masked_evidence_package`, `list_evidence_templates`, `get_sanitized_jira_ticket`.
- `evidence-gate` CLI: `decisions`, `audit-events`, `audit-export`, `metrics`, `retention-cleanup`, `approvals` subcommands.
- `evidence_gate/.data/` gitignored; `EVIDENCE_GATE_DATA_DIR` env var.
