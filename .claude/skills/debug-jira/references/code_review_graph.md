# code-review-graph Usage

## When available
Check with `code-review-graph status --repo <path>` (CLI) or `list_graph_stats_tool` (MCP). If the graph is built and fresh, prefer graph tools over Grep/Glob.

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

## Tool catalogue (upstream: github.com/tirth8205/code-review-graph)

The MCP server exposes 29 tools. All names end with the `_tool` suffix and are
addressed as `mcp__code-review-graph__<name>` from this project. The grouping
below mirrors the upstream README.

### Core graph operations
- `build_or_update_graph_tool` — build or incrementally update the graph (CLI equivalent: `code-review-graph build|update --repo <path>`).
- `get_minimal_context_tool` — ultra-compact context (~100 tokens); call this first when you only need a structural sketch.
- `get_impact_radius_tool` — blast radius of changed files.
- `get_review_context_tool` — token-optimised review context with structural summary and source snippets.

### Query & traversal
- `query_graph_tool` — predefined patterns: `callers_of`, `callees_of`, `tests_for`, `imports_of`, `importers_of`, `children_of`, `inheritors_of`, `file_summary`.
- `traverse_graph_tool` — BFS/DFS traversal from any node with a token budget.
- `semantic_search_nodes_tool` — search code entities by name or meaning (FTS / vector hybrid).

### Analysis & detection
- `embed_graph_tool` — compute vector embeddings to enable semantic search.
- `list_graph_stats_tool` — graph size and health.
- `find_large_functions_tool` — functions/classes exceeding a line-count threshold.
- `detect_changes_tool` — risk-scored change impact analysis for code review.

### Flows & communities
- `list_flows_tool` — execution flows sorted by criticality.
- `get_flow_tool` — details of one execution flow.
- `get_affected_flows_tool` — flows touched by changed files.
- `list_communities_tool` — detected code communities.
- `get_community_tool` — details of one community.

### Architecture & insights
- `get_architecture_overview_tool` — overview from community structure.
- `get_hub_nodes_tool` — most-connected nodes (architectural hotspots).
- `get_bridge_nodes_tool` — chokepoints via betweenness centrality.
- `get_knowledge_gaps_tool` — structural weaknesses and untested hotspots.
- `get_surprising_connections_tool` — unexpected cross-community coupling.
- `get_suggested_questions_tool` — auto-generated review questions.

### Documentation & refactoring
- `get_docs_section_tool` — retrieve documentation sections.
- `generate_wiki_tool` — generate markdown wiki from communities.
- `get_wiki_page_tool` — retrieve a specific wiki page.
- `refactor_tool` — rename preview, dead-code detection, suggestions.
- `apply_refactor_tool` — apply a previously previewed refactoring.

### Multi-repo
- `list_repos_tool` — list repositories registered in the CRG registry.
- `cross_repo_search_tool` — search across all registered repositories.

> **Repo enumeration in debug-jira is not done through code-review-graph.**
> The workflow reads `.claude/skills/debug-repo/registry.json` directly as its
> sole source of scannable repos — do not call `list_repos_tool` for
> enumeration. The graph tools above operate against repos already resolved
> from that registry. `cross_repo_search_tool` is fine when the search itself
> needs to span multiple registered repos.

## Calling pattern in MCP

Most tools accept `repo_root` (absolute path) or auto-detect from cwd. The
project's CRG registry resolves an alias → graph DB; pass the same repo path
that appears in `.claude/skills/debug-repo/registry.json`.

```
mcp__code-review-graph__semantic_search_nodes_tool(
  query="OtpService", repo_root="/home/myadmin/tools/projects/cdcn-auth-service",
  kind="Function", limit=20)

mcp__code-review-graph__query_graph_tool(
  pattern="callers_of", target="OtpService.checkMaxSendOtp",
  repo_root="/home/myadmin/tools/projects/cdcn-auth-service")
```

## Picking the right tool for a debug-jira scan

1. **First lead — function/class by keyword:** `semantic_search_nodes_tool`.
2. **Walk callers/callees/tests after the first lead:** `query_graph_tool` with the relevant pattern. Skip `grep` for these — the graph already has the edges.
3. **Read a single file's structure cheaply:** `query_graph_tool` `pattern=file_summary` instead of `Read` over the whole file.
4. **Token-bounded source snippets across a change set:** `get_review_context_tool`.
5. **Blast radius of a suspected buggy function:** `get_impact_radius_tool`.
6. **Which execution paths a suspected change touches:** `get_affected_flows_tool` (after the flow set has been built — `list_flows_tool` to confirm).
7. **Architectural orientation on an unfamiliar repo:** `get_architecture_overview_tool` + `list_communities_tool`.
8. **Cross-repo lookups (e.g. caller in one service, callee in another):** `cross_repo_search_tool`.

## Recording graph usage
Record every graph call in the service_repo_map entry's `graph_queries_used` field — both the CLI commands (`code-review-graph status|update|build`) and the MCP tool names with their key arguments. The entry is what makes a debug session reproducible.
