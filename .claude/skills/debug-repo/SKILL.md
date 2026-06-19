---
name: Debug Repo
description: Manage the service repository registry for the debb debugging system — register, list, update, or delete entries that record each service's local path, domain tags, and per-environment connections (Quickwit indices, Metabase databases, Prometheus jobs). This registry is the sole source of scannable repos for the debug-jira skill (which reads `.claude/skills/debug-repo/registry.json` directly and never calls code-review-graph `list_repos_tool` for enumeration). Registry mutations (register/delete/update) are local-only. The code-review-graph is a single combined graph built at the workspace root (the common parent of all registered repos, e.g. `.../vds`) and registered in ~/.code-review-graph/registry.json under one alias, so the graph MCP tools (semantic_search_nodes, query_graph, etc.) resolve the whole workspace from one DB; (re)build it with the skill's `setup-graph` operation (and migrate off the old per-repo model once with `migrate-graph`). Use whenever the user wants to add, remove, edit, or inspect a service repo in the registry, or asks to "register a repo", "list registered repos", "update repo connection", "remove a repo from the registry", or invokes /debug-repo.
allowed-tools: Read, Write, Edit, Bash, AskUserQuestion
---

# Debug Repo

Manages `registry.json` — the source-of-truth list of service repositories that the **debug-jira** skill scans during incident triage. Each entry records:

- **name** — unique service repo identifier (used as primary key)
- **description** — short human-readable summary
- **path** — absolute local filesystem path to the repo
- **tags** — domain categorization tags (e.g. `payments`, `auth`, `ingest`)
- **connection** — list of `{ environment, sources[] }` entries; each source has `name` (one of: `quickwit`, `metabase`, `prometheus`) and a typed `metadata` object

## Workflow

When the user invokes this skill, present the four options and route to the matching subroutine. **Always run the helper script (`scripts/registry.py`) for the actual data mutation** — it owns validation, atomic writes, and schema enforcement. Do not hand-edit `registry.json`.

### Step 1 — Determine the operation

If the user's intent is unambiguous from their message (e.g. "register my new repo X"), skip the menu. Otherwise, ask:

```
1. Register a new service repo
2. List all registered service repos
3. Update an existing service repo
4. Delete a service repo
```

Use `AskUserQuestion` for the menu when intent is unclear.

### Step 2 — Collect inputs (hybrid)

Default to **interactive prompts** (one field at a time via `AskUserQuestion` or plain prompts). If the user says "I'll paste JSON" or supplies a JSON object up front, accept that path instead — validate it against `schemas/registry_entry.schema.json` before writing.

Required fields per the schema in `schemas/registry_entry.schema.json`:

| Field | Type | Notes |
|---|---|---|
| `name` | string | Unique. Reject if it collides with an existing entry on register. |
| `description` | string | Short purpose summary. |
| `path` | string | Absolute path. Verify it exists and is a directory before saving. |
| `tags` | array<string> | At least one tag. Lowercase, kebab-case recommended. |
| `connection` | array | At least one environment block. See per-source schemas. |

For each `connection[i]`:
- `environment` — one of `production`, `uat`, `staging`, `dev` (extensible — warn but accept other values).
- `sources` — optional; each source's `metadata` must match the schema for its `name`. See `references/source_types.md`.

### Step 3 — Run the operation

Invoke the helper script. Pass JSON over stdin where applicable so the user's literal values are preserved:

```bash
python .claude/skills/debug-repo/scripts/registry.py register   # reads JSON entry from stdin
python .claude/skills/debug-repo/scripts/registry.py list       # prints table or --json
python .claude/skills/debug-repo/scripts/registry.py update <name>  # reads patch JSON from stdin
python .claude/skills/debug-repo/scripts/registry.py delete <name> --confirm
python .claude/skills/debug-repo/scripts/registry.py show <name>    # prints one entry
python .claude/skills/debug-repo/scripts/registry.py setup-graph    # build the combined graph at the workspace root
python .claude/skills/debug-repo/scripts/registry.py migrate-graph --confirm  # one-time: per-repo → combined
```

The script writes to `.claude/skills/debug-repo/registry.json` (atomic temp-file rename). It exits non-zero on validation failure with a JSON error on stderr; relay the error verbatim to the user.

**Update merge is shallow.** The `update` patch is merged top-level only — patch keys replace the matching keys in the existing entry, they don't deep-merge. To add a source to an existing environment block, the patch must include the **full** `connection` array (existing environments + their existing sources + the new source). To safely build that patch, first run `show <name>`, modify the JSON in place, and pipe the whole thing to `update`. Never send a partial `connection` array — it will replace the whole array and silently drop other environments.

### Code-review-graph (combined workspace graph)

The graph is **one combined graph** built at the workspace root — the common parent of all registered repos (e.g. `.../vds`) — not a graph per repo. `register`, `update`, and `delete` are **local-only**: they mutate `registry.json` and never touch the graph. Two explicit operations manage the graph:

- **`setup-graph`** — (re)build the combined graph at the workspace root. Runs, in order:
  1. `code-review-graph install --repo <root> --platform claude-code -y` — write the MCP config (`.mcp.json`), Claude Code hooks, and inject graph instructions into the root's `CLAUDE.md`; ensure `.gitignore` ignores `.code-review-graph/`.
  2. `code-review-graph build --repo <root>` — build the single combined graph over the whole workspace tree.
  3. `code-review-graph register <root> --alias <root-name>` — register the workspace root under one alias (default: the root directory name, e.g. `vds`). **Runs last on purpose:** CRG's `register` rejects a path with no `.git`/`.code-review-graph`, and `build` is what creates `.code-review-graph`.

  Run it after registering/deleting repos so the graph reflects the current registry. Reports `graph_register`, `graph_install`, `graph_build`.

- **`migrate-graph --confirm`** — one-time migration off the old per-repo model. Unregisters every per-repo CRG alias under the workspace root, **deletes** each sub-repo's stale `.code-review-graph/` directory, then runs the same `setup-graph` steps. Reports `unregistered_aliases`, `removed_graph_dirs`, then the `setup-graph` fields.

**Warn before `setup-graph` / `migrate-graph`.** The build re-parses the entire workspace (125+ services) and can take **minutes**. `install` writes/modifies `.mcp.json`, `CLAUDE.md`, and `.gitignore` at the workspace root. `migrate-graph` additionally **deletes** per-repo `.code-review-graph/` directories and unregisters their aliases — show the user what will be removed and get explicit confirmation before passing `--confirm`.

**Best-effort, no rollback.** Each CRG step is reported independently; a failure in one does not undo the others or the local registry. Common issues: CRG CLI missing (`pip install code-review-graph`); already-registered/not-found drift (safe to mention and ignore); build timeout (raise `--timeout`, default 1800s, or rerun `setup-graph`). The workspace root does **not** need to be a git repo — `build`/`install` walk the filesystem.

**Flags (both `setup-graph` and `migrate-graph`):**

- `--alias <name>` — override the workspace-root alias (default: root directory name).
- `--no-install` — register (and build) but skip the `install` step.
- `--no-build` — register (and install) but skip the heavy full build; rerun `setup-graph` later.
- `--timeout <seconds>` — build timeout (default: 1800).

`update`, like `register`/`delete`, never touches the graph.

### Step 4 — Confirm and report

After a successful mutation, echo back the diff (added/changed/removed fields) so the user can verify. For deletes, show the entry that was removed and ask for explicit confirmation **before** invoking the script with `--confirm`.

For list operations, render a compact table with name, tags, environments, and source counts. Offer `--json` if the user wants the raw shape.

## Hard rules

- **Never silently overwrite an existing entry.** `register` must fail if `name` already exists; the user must explicitly choose `update` instead.
- **Never delete without explicit confirmation.** Show the entry, then ask "Delete <name>? (yes/no)" — only proceed on a literal "yes".
- **Never invent paths, tags, or source metadata.** If the user is missing a required field, ask. Do not fabricate values to make the command go through.
- **Path must be absolute and exist.** If it doesn't, surface the error and ask the user to fix it.
- **Source metadata is typed.** Reject `quickwit` sources missing `id` and `uid`, `metabase` sources missing `database`, `prometheus` sources missing `job`.

## Integration with debug-jira

The `debug-jira` skill's repo-mapping step reads this registry as the authoritative scannable-repo list. See `references/debug_jira_integration.md` for the contract and the consumer-side query helpers.

When you change the registry, mention to the user: "debug-jira will pick up this change on its next run."

**Graph freshness contract.** The combined graph is **not** rebuilt on every registry mutation — `register`/`delete` are local-only. Run `setup-graph` after adding or removing repos to fold the change into the combined graph. `debug-jira` is responsible for refreshing the combined graph at the workspace root (`code-review-graph update --repo <root>`, with `build` as fallback) at the start of each scan, so the index reflects current HEADs at debug time. Do not extend this skill to refresh on every list/show — the cost belongs at scan time, not registry time.

## Reference files

- `schemas/registry.schema.json` — top-level registry shape (array of entries).
- `schemas/registry_entry.schema.json` — one entry's shape.
- `schemas/source_quickwit.schema.json`, `source_metabase.schema.json`, `source_prometheus.schema.json` — typed source metadata.
- `references/source_types.md` — what each source's `metadata` means and where to find the values.
- `references/debug_jira_integration.md` — how this registry feeds debug-jira.
- `scripts/registry.py` — the helper script. Read it before extending behavior.
