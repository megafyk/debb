# debug-jira integration

The `debug-repo` registry is the authoritative list of scannable repos for the
`debug-jira` workflow's repo-mapping step.

## Contract

`debug-jira` reads `.claude/skills/debug-repo/registry.json` (the same file
this skill writes) before doing any code scan. For each candidate service the
triage step picks, the repo-mapping step:

1. Looks up the entry by `name` in the registry.
2. Uses `path` as the working directory for code-review-graph and Grep/Read.
3. Filters `connection[]` to the environment in scope (e.g. `production`).
4. Pulls Quickwit `id`/`uid` for log query plans, Metabase `database` for SQL
   query plans, and Prometheus `job` for metrics correlation.

If a candidate service has no registry entry, repo-mapping skips it and
records the gap so the engineer can either add the entry or rule the service
out.

## Why a separate registry from code-review-graph

`code-review-graph`'s `list_repos_tool` knows what's been parsed into the
graph. The debug-repo registry adds:

- **Per-environment connection metadata** — Quickwit indices, Metabase
  databases, Prometheus jobs. These don't belong in a code graph.
- **Domain tags** — used by triage to narrow candidates before scanning.
- **A short description** — gives the agent enough context to decide whether
  a repo is worth scanning at all.

The two registries are complementary. debug-jira may consult both: graph for
"is this scannable" and debug-repo for "where does it live and what data
sources back it."

### Automatic sync and build on register / delete

Since the two registries describe overlapping populations of repos, the
debug-repo skill now mirrors `register` and `delete` into CRG automatically,
and on register also parses the repo into the graph:

- `register` → `code-review-graph register <path> --alias <name>`, then `code-review-graph build --repo <path>` so the new repo is queryable from debug-jira immediately.
- `delete`  → `code-review-graph unregister <name>`.

The mapping is `debug-repo.name` ↔ `code-review-graph.alias` and
`debug-repo.path` ↔ `code-review-graph.path`. CRG only stores those two
fields, so updates to tags / connections / description never trigger a CRG
write or rebuild.

Both the sync and build are **best-effort, no rollback**. If CRG sync
fails (CLI not installed, non-git path, alias collision), the local
registry mutation still succeeds, the build is skipped, and the skill
surfaces the CRG error to the user. If sync succeeds but build fails
(parse error, timeout), the user can re-run `code-review-graph build
--repo <path>` manually. Drift is recoverable on both sides.

Flags:
- `--no-graph-sync` — skip the CRG register/unregister entirely (also skips build).
- `--no-graph-build` — register in CRG but skip the slower full-graph build.

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
