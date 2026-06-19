# debug-jira integration

The `debug-repo` registry is the authoritative list of scannable repos for the
`debug-jira` workflow's repo-mapping step.

## Contract

`debug-jira` reads `.claude/skills/debug-repo/registry.json` (the same file
this skill writes) before doing any code scan. For each candidate service the
triage step picks, the repo-mapping step:

1. Looks up the entry by `name` in the registry.
2. Uses `path` as the working directory for Grep/Read, and as a file-path filter
   when querying the combined code-review-graph (which spans every repo).
3. Filters `connection[]` to the environment in scope (e.g. `production`).
4. Pulls Quickwit `id`/`uid` for log query plans, Metabase `database` for SQL
   query plans, and Prometheus `job` for metrics correlation.

If a candidate service has no registry entry, repo-mapping skips it and
records the gap so the engineer can either add the entry or rule the service
out.

## Why a separate registry from code-review-graph

The debug-repo registry is the **sole** source of scannable repos for
debug-jira. The CRG (code-review-graph) registry at
`~/.code-review-graph/registry.json` holds a single entry for the workspace root
(alias e.g. `vds`) that points the graph MCP tools (`semantic_search_nodes`,
`query_graph`, etc.) at the one combined graph DB covering every service; it is
not the scannable-repo list, and debug-jira does not call `list_repos_tool` for
enumeration.

The debug-repo registry carries everything debug-jira needs that CRG does
not:

- **Per-environment connection metadata** — Quickwit indices, Metabase
  databases, Prometheus jobs. These don't belong in a code graph.
- **Domain tags** — used by triage to narrow candidates before scanning.
- **A short description** — gives the agent enough context to decide whether
  a repo is worth scanning at all.

### Building the combined workspace graph

The code-review-graph is a single combined graph at the **workspace root** (the
common parent of all registered repos, e.g. `.../vds`), not a graph per repo.
Registry mutations are decoupled from the graph:

- `register` / `update` / `delete` → **local-only**; they mutate `registry.json`
  and never touch CRG.
- `setup-graph` → `install --repo <root> --platform claude-code -y` (MCP config,
  hooks, CLAUDE.md injection at the root), then `build --repo <root>` (the
  combined graph over the whole tree), then `register <root> --alias <root-name>`
  (register last — CRG rejects a path with no `.git`/`.code-review-graph`, which
  `build` creates). Run after adding/removing repos.
- `migrate-graph --confirm` → one-time: unregister the old per-repo CRG aliases,
  delete each repo's `.code-review-graph/` dir, then `setup-graph`.

The combined graph spans every repo under the root, so a single MCP query
(`semantic_search_nodes`, `query_graph`, …) searches the whole workspace; scope
to one service by filtering on its `path` prefix.

Every CRG step is **best-effort, no rollback** and reported independently in the
script's JSON. The workspace root need not be a git repo — `build`/`install`
walk the filesystem. A full-workspace build can take minutes; raise `--timeout`
(default 1800s) or rerun `setup-graph` if it times out.

Flags (`setup-graph` and `migrate-graph`):
- `--alias <name>` — override the workspace-root alias (default: root dir name).
- `--no-install` — skip the `install` step.
- `--no-build` — skip the heavy full build (rerun `setup-graph` later).
- `--timeout <seconds>` — build timeout (default: 1800).

## Per-developer caveat

`path` is local to a developer's machine, so `registry.json` is
**gitignored**. Each developer maintains their own. The other fields (name,
description, tags, connection) are stable across machines, so teams often
share a seed file (e.g. `registry.example.json`) and developers fill in their
local paths after copying it.

## Reading the registry from another skill

Use the helper script with `--json`:

```bash
python .claude/skills/debug-repo/scripts/registry.py list --json
```

Or read the file directly — the schema in `schemas/registry.schema.json` is
stable and versioned. Bump `version` if you make a breaking change.
