# Code Scan Prompt

For each service in the service_repo_map, perform a targeted code scan.

**Precondition — refreshed graph.** This prompt runs *after* Step 3 of
`prompts/repo_mapping.md`, which mandates refreshing the code-review-graph
index for the target repo (`code-review-graph update --repo <path>`, falling
back to `build --repo <path>`). Do not start the scan against a graph that
has not been refreshed for this debug-jira session — a stale index drops
files, functions, log emitters, and tests added since the last build,
producing false-negative `log_fields` and downstream Quickwit plans that
silently miss real fields.

Priority order:
1. Use code-review-graph tools if available (semantic_search_nodes, query_graph callers_of/callees_of/tests_for).
2. Fall back to Grep/Glob/Read only if graph unavailable for this repo (refresh attempted and failed in repo_mapping Step 3).

Extract:
- Error handling paths and error codes
- **Log statements and their fields.** For each suspected code path, walk the
  reachable logger calls (`logger.info/warn/error/debug`, `log.info(...)`,
  structured-event emitters, MDC/context `put`s) and capture every structured
  field name they emit verbatim — kwargs, format keys, `extra=` dict keys, JSON
  event keys. These names become the **candidate pool** that Quickwit planning
  draws `fields_requested` from; nothing outside this pool is legal later.
- Database queries and entity references
- API endpoints and their handlers
- Input validation and normalization logic
- Related test files

Record all findings in the service_repo_map entry for each service. Log field
names go in `log_fields` exactly as they appear in code — do not normalize,
rename, or invent. If the suspected code paths emit no structured fields,
record `log_fields: []` and surface that gap before planning Quickwit.
