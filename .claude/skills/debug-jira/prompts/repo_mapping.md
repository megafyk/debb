# Repository Mapping Prompt

Using the triage summary and sanitized ticket context, build a service_repo_map.

## Step 1 — Enumerate registered repositories

Read `.claude/skills/debug-repo/registry.json` directly — that file is the
sole source of truth for which repos may be scanned. Equivalently, run
`python .claude/skills/debug-repo/scripts/registry.py list --json` if you
prefer the script-mediated path. Either way, the debug-repo registry is the
only enumeration channel:

- Do **not** call the code-review-graph MCP `list_repos_tool` for
  enumeration. The CRG registry at `~/.code-review-graph/registry.json` exists
  to let graph MCP tools resolve a repo alias to its graph DB; it is not the
  scannable-repo list.
- Do **not** consult `~/.code-review-graph/registry.json` directly.
- Do **not** invent a repo path.

Persist a verbatim copy of the registry JSON to
`debug_reports/<TICKET_ID>_<TRACE_ID>/repos/list_repos.json` immediately — this
is the audit trail for which repos were even considered. The Write tool with
the literal file contents is sufficient; no template needed.

If the registry has no entries, or the service the user mentions is not in
it, **stop and ask the user to register it** via the `debug-repo` skill
before proceeding.

Every entry already carries the metadata candidate selection and query
planning need: `path`, `name`, `description`, `tags`, and per-environment
`connection[]` with Quickwit `id`/`uid`, Metabase `database`/`tables`, and
Prometheus `job`. Use those fields directly — no follow-up tool call is
required to enrich them. If a required field (e.g. a Quickwit `uid` needed
for `datasource_uid`) is missing from the entry, surface the gap to the user
and ask — do not guess.

## Step 2 — Select candidate repos

From the registry result, pick candidates using sanitized Jira components,
service hints, stack hashes, error codes, and the registry's `tags` and
`description` fields. Filter `connection[]` to the environment in scope (e.g.
`production`). Record the selection reasoning per service in
`relevance_reason`.

Write the selection rationale to
`debug_reports/<TICKET_ID>_<TRACE_ID>/repos/candidates.md` as a short bullet
list — one line per repo (`<alias> — kept|dropped — <one-line reason>`).
Reviewers use this file to challenge the candidate set without re-deriving it
from the registry.

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
4. Check if code-review-graph is available after the refresh (`list_graph_stats_tool` MCP, or the CLI `status` exit code from step 3).
5. If graph is available, use `semantic_search_nodes` to find relevant functions/classes.
6. If graph is not available, use Grep/Glob to find relevant code.
7. Record: suspected code paths, functions, log fields, DB entities, SQL references.

Output `service_repo_map.md` as markdown — one section per service — with content covering every property in `schemas/service_repo_map.schema.json` (the schema is the field checklist, not the file format).

Do not include raw sensitive values. Use only secure value refs from the evidence session.
