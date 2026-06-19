# Query Plan Rules

## Quickwit plans must include
- service name
- datasource_uid matching a known Grafana data source for this service
- from and to (ISO 8601 preferred; bounds_checker narrows windows over 24h)
- at least one filter
- fields_requested — MUST be a subset of `service_repo_map.services[].log_fields` for the target service (the candidate pool produced by the code-scan step). Cross-check with ticket-named correlation/error fields, but never include fields the code does not emit. Never request all fields, never guess.
- max_hits <= 500
- output_profile name

## Metabase plans must include
- service name
- entity name
- query_intent describing what diagnostic facts are needed
- facts_requested list
- output_profile name
- For a live query: `sql_candidate` (an agent-authored native query) and `database_id` — evidence_gate rejects the query without them
- `schema`, when set, must be a bare SQL identifier (`[A-Za-z_][A-Za-z0-9_]*`) — anything else is rejected before execution
- Results are capped at 500 rows; design aggregating / `LIMIT`-bearing queries rather than expecting full table dumps

## Plans must not include
- Raw sensitive values (use value_ref instead)
- `SELECT *` or mutating SQL (DROP/TRUNCATE/DELETE/ALTER/CREATE/INSERT/UPDATE), `UNION SELECT`, `INTO OUTFILE`, `LOAD_FILE` — the safety gate rejects these
- Unbounded time windows
- Missing service context

## Replan policy (Quickwit)
- A `QuickwitQueryResult` with `is_valuable=false` (`reason="zero_hits"`) means the plan returned nothing. Revise one knob — time window, filter set, fields_requested, or datasource_uid — and resubmit a new plan via `create_quickwit_evidence_request`. Cap attempts at 3.

## Three-stage strategy — Quickwit only (see `prompts/quickwit_query_planning.md`)

Does NOT apply to Metabase. A Metabase plan carries one agent-authored `sql_candidate` (native query) and has no request journey to correlate.

- **Stage 1** narrows by error string + level + env + masked user input to find the failing request and surface correlation IDs in `masked_data.correlation_ids`.
- **Stage 2** pulls the full journey by `contextMap.traceId` (no level filter, no instance filter — cross-service).
- **Stage 3** falls back through `correlationID → requestID → sessionID` if stage 2 is empty. Cap the chain at 3 attempts.
