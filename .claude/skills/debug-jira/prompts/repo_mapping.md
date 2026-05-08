# Repository Mapping Prompt

Using the triage summary and sanitized ticket context, build a service_repo_map.

## Step 1 — Enumerate registered repositories

The authoritative scannable-repo list is the **debug-repo registry** at
`.claude/skills/debug-repo/registry.json`. Read it via:

```bash
python .claude/skills/debug-repo/scripts/registry.py list --json
```

This returns every entry with its `name`, `description`, `path`, `tags`, and
per-environment `connection[]` (Quickwit `id`/`uid`, Metabase `database`,
Prometheus `job`). Treat this as the source of truth — do not scan repos that
are not in this registry.

If the registry is empty or missing the service the user mentions, **stop and
ask the user to register it** via the `debug-repo` skill before proceeding.
Do not invent a repo path.

You may additionally call the code-review-graph MCP `list_repos_tool` to
check which entries are also parsed into the graph; prefer those for
structural queries.

## Step 2 — Select candidate repos

From the registry result, pick candidates using sanitized Jira components,
service hints, stack hashes, error codes, and the registry's `tags` and
`description` fields. Filter `connection[]` to the environment in scope (e.g.
`production`). Record the selection reasoning per service in
`relevance_reason`.

## Step 3 — Map each candidate service

For each selected service:

1. Identify the repository path (from the registry entry).
2. Read AGENTS.md or CLAUDE.md from the repository root.
3. **Refresh the code-review-graph index for this repo before any graph
   query.** This is mandatory — the registration-time build only seeds the
   graph once; the developer's checkout may have advanced since.

   ```bash
   # Incremental — preferred (only re-parses files changed since HEAD~1)
   code-review-graph update --repo <path>

   # Full rebuild — fall back when the graph is missing, corrupt, or the
   # working tree has moved more than a handful of commits past the last
   # index. Build also re-runs flow/community postprocessing.
   code-review-graph build --repo <path>

   # Verify the graph reflects HEAD before scanning
   code-review-graph status --repo <path>
   ```

   Record the command(s) you ran in the service_repo_map entry's
   `graph_queries_used` (e.g. `"code-review-graph update --repo /…"`). If
   both update and build fail, mark `code_review_graph_available: false`
   for this repo and proceed with the Grep/Glob fallback only — do not
   query a stale graph.
4. Check if code-review-graph is available after the refresh
   (`graph-status` MCP tool, or the CLI `status` exit code from step 3).
5. If graph is available, use `semantic_search_nodes` to find relevant functions/classes.
6. If graph is not available, use Grep/Glob to find relevant code.
7. Record: suspected code paths, functions, log fields, DB entities, SQL references.

Output the service_repo_map following the schema in `schemas/service_repo_map.schema.json`.

Do not include raw sensitive values. Use only secure value refs from the evidence session.
