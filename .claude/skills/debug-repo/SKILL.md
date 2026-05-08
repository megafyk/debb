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

`register` and `delete` automatically mirror the change into the
`code-review-graph` multi-repo registry at `~/.code-review-graph/registry.json`:

- **register** runs `code-review-graph register <path> --alias <name>`, then `code-review-graph build --repo <path>` to parse the new repo into the graph.
- **delete** runs `code-review-graph unregister <name>`.

The CRG outcome is reported in the JSON response under `graph_sync` (the
register/unregister step) and `graph_build` (the parse step, register-only):

```json
"graph_sync":  { "ran": true, "ok": true, "command": "...", "stdout": "Registered: ...", "stderr": "" },
"graph_build": { "ran": true, "ok": true, "command": "...", "stdout": "Full build: 12 files, 348 nodes, 921 edges (postprocess=full)", "stderr": "..." }
```

**Build can take a minute or more.** A real service repo with hundreds of
files takes seconds-to-minutes to parse. Before kicking off `register`,
warn the user that the command will block until the graph build finishes
("this will register the repo and then build its graph; that may take a
minute"). Then run it and report both `graph_sync` and `graph_build`
outcomes back to the user.

**Best-effort, no rollback.** If `graph_sync` fails (CRG CLI missing,
non-git path, alias collision, network hiccup), the local registry
mutation still succeeds and `graph_build` is skipped automatically — no
point parsing a repo CRG doesn't know about. Surface the `graph_sync.stderr`
to the user. Common causes:

- `Path does not look like a repository (no .git or .code-review-graph)` — the user gave a path that isn't a git repo. Ask them to either `git init` it or pick the correct path, then re-run.
- `code-review-graph CLI not found on PATH` — CRG isn't installed. The local register still succeeded; tell the user how to install it (`pip install code-review-graph`) or to pass `--no-graph-sync`.
- `Repository already registered` (on register) or `not found` (on unregister) — the two registries had drifted. Usually safe to ignore; mention it to the user.

If `graph_build` fails (parse error on a specific file, postprocess
failure, timeout), the local register *and* the CRG register both still
succeeded — only the graph parse was incomplete. Surface the build error;
the user can re-run `code-review-graph build --repo <path>` manually to
retry, or pass `--no-graph-build` next time and build later.

**Opting out.** Two flags control the CRG side:

- `--no-graph-sync` — skip both the CRG register/unregister AND the build. Use when the user wants the change to stay local, or is registering a non-git directory on purpose.
- `--no-graph-build` — register in CRG, but skip the slower graph build. Use when the user is registering a large repo and wants to defer the build to a quieter moment, or has their own build automation. Only meaningful on `register`.

`update` does **not** touch CRG — CRG only stores `{path, alias}` per repo, and our `update` doesn't allow renaming, so there's nothing to sync or rebuild.

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
