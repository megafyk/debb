# code-review-graph Usage

## When available
Check with `graph-status`. If the graph is built, prefer graph tools over Grep/Glob.

## Refreshing the index (mandatory before scan)

The graph reflects the developer's local checkout at the time of the last
build. The debug-repo skill builds the graph once at registration; if the
developer pulls new commits afterward, the index goes stale. Before any scan
in a debug-jira session, refresh **every candidate repo** picked in
repo-mapping:

```bash
# Incremental — preferred. Only re-parses files changed since HEAD~1.
code-review-graph update --repo <path>

# Full rebuild — fall back when:
#   - the graph is missing (first scan since registration was skipped),
#   - update fails (corrupt sqlite, schema mismatch),
#   - the working tree has moved more commits past the last index than
#     `update --base HEAD~1` can catch.
# Build also re-runs flow/community postprocessing.
code-review-graph build --repo <path>

# Verify before any query
code-review-graph status --repo <path>
```

Record the exact command in the service_repo_map entry's `graph_queries_used`
so the report is reproducible. If both update and build fail for a repo, set
`code_review_graph_available: false` for that repo and use Grep/Glob — never
query a stale graph silently.

Why this matters: a stale graph causes false negatives in
`semantic_search_nodes`, `query_graph`, and `get_minimal_context`. Missed log
emitters drop fields from the candidate pool that
`prompts/quickwit_query_planning.md` draws from, so downstream Quickwit plans
silently omit real fields and the connector returns zero hits — wasting a
replan attempt.

## Key tools for debugging

### list_repos_tool
Enumerate every repository registered in the code-review-graph registry. Call this **first** during repo mapping — it is the authoritative source for which repos can be scanned. Use the result together with sanitized Jira components, service hints, error codes, and ownership metadata to pick candidate repos. Do not scan repos that are not in the registry.

### semantic_search_nodes
Find functions/classes by keyword. Use for initial discovery.
```
semantic_search_nodes("login failure phone normalization")
```

### query_graph
Trace relationships:
- `callers_of`: who calls this function
- `callees_of`: what this function calls
- `tests_for`: test coverage
- `imports_of`: module dependencies

### get_impact_radius
Understand blast radius of a suspected buggy function.

### get_affected_flows
Find execution paths through a suspected code area.

## Recording graph usage
Record all graph queries in the service_repo_map `graph_queries_used` field.
