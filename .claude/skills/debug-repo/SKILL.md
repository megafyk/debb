---
name: Debug Repo
description: Manage the service repository registry for the debb debugging system — register, list, update, or delete entries that record each service's local path, domain tags, and per-environment connections (Quickwit indices, Metabase databases, Prometheus jobs). On register/delete, the skill also mirrors the change into the code-review-graph multi-repo registry at ~/.code-review-graph/registry.json so graph queries and debug-jira stay in sync. Use whenever the user wants to add, remove, edit, or inspect a service repo in the registry, or asks to "register a repo", "list registered repos", "update repo connection", "remove a repo from the registry", or invokes /debug-repo.
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
```

The script writes to `.claude/skills/debug-repo/registry.json` (atomic temp-file rename). It exits non-zero on validation failure with a JSON error on stderr; relay the error verbatim to the user.

**Update merge is shallow.** The `update` patch is merged top-level only — patch keys replace the matching keys in the existing entry, they don't deep-merge. To add a source to an existing environment block, the patch must include the **full** `connection` array (existing environments + their existing sources + the new source). To safely build that patch, first run `show <name>`, modify the JSON in place, and pipe the whole thing to `update`. Never send a partial `connection` array — it will replace the whole array and silently drop other environments.

### Code-review-graph sync (register and delete only)

`register` and `delete` mirror the change into `~/.code-review-graph/registry.json`:

- **register** runs `code-review-graph register <path> --alias <name>` then `code-review-graph build --repo <path>`.
- **delete** runs `code-review-graph unregister <name>`.

The script reports both outcomes under `graph_sync` (register/unregister) and `graph_build` (register only) in its JSON response. Surface them to the user verbatim.

**Warn before `register`.** The build can take seconds to minutes on a real service repo. Tell the user it will block until the build finishes.

**Best-effort, no rollback.** If `graph_sync` or `graph_build` fails, the local registry mutation still succeeds. Common `graph_sync` failures: path is not a git repo (suggest `git init` or fix the path); CRG CLI missing (`pip install code-review-graph` or use `--no-graph-sync`); already-registered/not-found drift (usually safe to mention and ignore). `graph_build` failures leave both registries intact — the user can retry `code-review-graph build --repo <path>` later.

**Opt-out flags:**

- `--no-graph-sync` — skip CRG sync and build entirely (local-only or non-git path).
- `--no-graph-build` — register in CRG but skip the build (defer to a quieter moment). `register` only.

`update` does not touch CRG — CRG only stores `{path, alias}`, and `update` doesn't rename.

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

**Graph freshness contract.** The `code-review-graph build` we run at register time is a **seed** — it makes the repo immediately queryable, but it does not stay current as the developer pulls new commits. `debug-jira` is responsible for running `code-review-graph update --repo <path>` (with `build` as fallback) for every candidate repo at the start of each scan, so the index reflects HEAD at debug time. Do not extend this skill to refresh on every list/show — the cost belongs at scan time, not registry time.

## Reference files

- `schemas/registry.schema.json` — top-level registry shape (array of entries).
- `schemas/registry_entry.schema.json` — one entry's shape.
- `schemas/source_quickwit.schema.json`, `source_metabase.schema.json`, `source_prometheus.schema.json` — typed source metadata.
- `references/source_types.md` — what each source's `metadata` means and where to find the values.
- `references/debug_jira_integration.md` — how this registry feeds debug-jira.
- `scripts/registry.py` — the helper script. Read it before extending behavior.
