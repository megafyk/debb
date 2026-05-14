# debb

AI-assisted production debugging system. An agent skill + trust-boundary service that lets AI coding assistants (Claude Code, Codex) investigate Jira tickets using production evidence — without ever seeing raw PII, credentials, or unredacted logs.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  AI Agent (Claude Code / Codex)                     │
│  └─ .claude/skills/debug-jira/  (skill definition)  │
└──────────────────┬──────────────────────────────────┘
                   │ MCP (stdio)
┌──────────────────▼──────────────────────────────────┐
│  evidence_gate                                       │
│  ┌────────────┐ ┌────────────┐ ┌────────────────┐  │
│  │  Sessions  │ │  Redaction │ │  Audit Logger  │  │
│  └─────┬──────┘ └─────┬──────┘ └────────────────┘  │
│  ┌─────▼──────┐ ┌─────▼──────┐ ┌────────────────┐  │
│  │ Connectors │ │  Request   │ │  Masked Pkg    │  │
│  │ Jira/QW/MB │ │  Pipeline  │ │  Store         │  │
│  └────────────┘ └────────────┘ └────────────────┘  │
└─────────────────────────────────────────────────────┘
         │                │                │
    Jira Cloud      Quickwit logs     Metabase DB
```

**Key invariant:** The agent never sees raw production data. All evidence passes through redaction before being returned.

## MCP Tools

The repo's `.mcp.json` registers two stdio MCP servers:

### `evidence_gate` (this repo) — 8 tools

| Tool | Purpose |
|------|---------|
| `start_debugging_session` | Create session for a Jira ticket |
| `get_sanitized_jira_ticket` | Get redacted ticket context |
| `create_quickwit_evidence_request` | Submit a log query plan |
| `create_metabase_evidence_request` | Submit a DB query plan |
| `get_evidence_request_status` | Check request state |
| `get_masked_evidence_package` | Retrieve redacted results |
| `list_evidence_templates` | List registered Metabase query templates |
| `submit_debug_report` | Submit final root-cause report |

### `code-review-graph` (external — github.com/tirth8205/code-review-graph) — 29 tools

Used by **debug-jira** for code scanning before query planning. From MCP these
are addressed as `mcp__code-review-graph__<name>`. Highlights:

| Tool | Purpose |
|------|---------|
| `semantic_search_nodes_tool` | Find functions/classes/files by name or meaning |
| `query_graph_tool` | Traverse callers, callees, imports, tests, file_summary, children, inheritors |
| `get_minimal_context_tool` | ~100-token sketch of a node's neighbourhood |
| `get_review_context_tool` | Token-efficient source snippets across changed files |
| `get_impact_radius_tool` | Blast radius of a change |
| `get_affected_flows_tool` | Execution paths impacted by a change |
| `traverse_graph_tool` | BFS/DFS from a node with a token budget |
| `detect_changes_tool` | Risk-scored change-impact analysis |
| `get_architecture_overview_tool` / `list_communities_tool` | Architectural orientation |
| `get_hub_nodes_tool` / `get_bridge_nodes_tool` | Hotspots & chokepoints |
| `find_large_functions_tool` | Locate oversized functions |
| `refactor_tool` / `apply_refactor_tool` | Plan and apply renames / dead-code removals |
| `list_graph_stats_tool` | Verify the graph is built and fresh |
| `cross_repo_search_tool` | Search across all CRG-registered repos |

Full 29-tool catalogue (grouped by upstream README sections) and a picking
guide live in
[`.claude/skills/debug-jira/references/code_review_graph.md`](.claude/skills/debug-jira/references/code_review_graph.md).
Repo enumeration in **debug-jira** is **not** done through `list_repos_tool` —
the workflow reads `.claude/skills/debug-repo/registry.json` directly.

## Quick Start

```bash
# Prerequisites: Python 3.12+, uv
uv sync

# Copy and configure environment
cp .env.example .env
# Edit .env with your Jira/Quickwit/Metabase credentials
# (Leave URLs empty to run in fixture mode — no real services needed.)

# Run tests (fixture mode, no credentials required)
make test
```

## Running the MCP server

`evidence_gate` is a stdio MCP server. It is normally launched by an MCP client (Claude Code, Codex, etc.) — not run by hand — but you can sanity-check it standalone:

```bash
# Standalone (process waits on stdio; Ctrl-C to exit)
uv run --package evidence-gate python -m evidence_gate.main
```

### Wiring it into Claude Code

The repo ships with a `.mcp.json` that registers both `evidence_gate` and `code-review-graph`. When you open the project in Claude Code, both servers start automatically — no extra setup needed. The relevant entry:

```jsonc
{
  "mcpServers": {
    "evidence_gate": {
      "command": "uv",
      "args": ["run", "--package", "evidence-gate", "python", "-m", "evidence_gate.main"],
      "type": "stdio"
    },
    "code-review-graph": {
      "command": "uvx",
      "args": ["code-review-graph", "serve"],
      "type": "stdio"
    }
  }
}
```

Claude Code launches each server with the project root as the working directory, so `uv run --package evidence-gate` resolves the workspace member without needing an explicit `--directory`.

After that, the `Debug Jira` skill in `.claude/skills/debug-jira/` can drive the full flow. Open a Claude Code session in this repo and ask it to debug a Jira ticket — the skill calls `start_debugging_session`, builds query plans, submits evidence requests, and writes a report (see [How It Works](#how-it-works)).

### End-to-end sanity check (fixture mode)

With empty URLs in `.env`, every connector returns synthetic data and no real Jira / Quickwit / Metabase access is needed. The full pipeline is exercised by:

```bash
uv run --package evidence-gate pytest evidence_gate/tests/test_full_flow_eval.py -v
```

This runs `start_debugging_session → query plans → evidence requests → masked packages → report submission` against fixtures end-to-end.

## Project Structure

```
.claude/skills/
  debug-jira/                # Main skill: Jira ticket → masked evidence → report
  debug-repo/                # Registry skill: register/list/update/delete service repos
                             # consumed by debug-jira; mirrors into code-review-graph
evidence_gate/
  evidence_gate/
    main.py                  # MCP server entry point
    config.py                # Settings (EVIDENCE_GATE_* env vars)
    contracts.py             # Pydantic domain models
    audit_logger.py          # Append-only audit log
    connectors/              # Jira, Quickwit, Metabase (live + fixture mode)
    redaction/               # PII extraction, log/DB/Jira redaction, leakage patterns
    request_services/        # Schema/safety/bounds checks, executor, report reviewer
    storage/                 # Session, sensitive-value, request, raw + masked + debug-report stores
    mcp_server/              # MCP stdio server, tool registration (8 tools)
  tests/                     # 214 tests
    boundary/                # 28 trust-boundary tests
docs/
  debugging_system_implementation_plan.md  # Section 3 main flow, 3.1 alternative
  log.md                     # ADR (architecture decision record)
debug_reports/               # Per-session masked-evidence JSONL (gitignored)
  <JIRA_TICKET_ID>_<OTEL_TRACE_ID>/evidence/EVID-<id>.jsonl
```

## How It Works

1. Engineer asks the AI agent to debug a Jira ticket
2. Agent invokes the **Debug Jira** skill
3. Skill calls `start_debugging_session` → gets a session ID
4. Skill calls `get_sanitized_jira_ticket` → gets PII-redacted ticket context
5. Skill consults the **debug-repo** registry to pick candidate service repos (see [Registering service repos](#registering-service-repos))
6. Agent builds query plans (log searches, DB lookups) grounded in code
7. Skill submits plans → evidence_gate validates (schema, safety, bounds)
8. evidence_gate executes against Quickwit/Metabase, redacts results, and writes the masked records to `debug_reports/<JIRA_TICKET_ID>_<OTEL_TRACE_ID>/evidence/EVID-<id>.jsonl` (one record per line)
9. Agent receives a masked evidence package whose `evidence_file: {path, format, line_count}` points at that JSONL
10. Agent writes a debug report citing evidence IDs, code paths, and individual hits as `<path>:L<n>`
11. Skill submits report → programmatic review checks for leakage

## Registering service repos

`debug-jira` only scans repos listed in the **debug-repo registry** at `.claude/skills/debug-repo/registry.json`. Each entry records a service's local path, domain tags, and per-environment connections (Quickwit index, Metabase database, Prometheus job). The registry is gitignored — paths are per-developer.

When `debug-jira` cannot find a candidate service in the registry, the recovery path is the **debug-repo** skill, not a path guess:

```bash
# Interactive: register a new service repo
/debug-repo

# Or, if the intent is unambiguous:
"register repo payments-api"
```

`register` and `delete` mirror the change into `~/.code-review-graph/registry.json` and (on register) parse the repo into the graph so it is queryable from the next `debug-jira` run. See **Section 3.1** of [docs/debugging_system_implementation_plan.md](docs/debugging_system_implementation_plan.md) for the full flow and the trust-boundary contract.

## Configuration

All settings use the `EVIDENCE_GATE_` prefix:

| Variable | Purpose |
|----------|---------|
| `EVIDENCE_GATE_JIRA_BASE_URL` | Jira Cloud instance URL |
| `EVIDENCE_GATE_JIRA_USERNAME` | Atlassian email |
| `EVIDENCE_GATE_JIRA_PASSWORD` | Atlassian API token |
| `EVIDENCE_GATE_QUICKWIT_URL` | Quickwit search endpoint (Grafana `/ds/query` proxy) |
| `EVIDENCE_GATE_QUICKWIT_USERNAME` | Quickwit Basic Auth user |
| `EVIDENCE_GATE_QUICKWIT_PASSWORD` | Quickwit Basic Auth password |
| `EVIDENCE_GATE_QUICKWIT_ORG_ID` | Grafana org that owns the data source (0 = omit `X-Grafana-Org-Id`) |
| `EVIDENCE_GATE_PROJECT_ROOT` | *Optional.* Override for `debug_reports/` location (default: repo root) |
| `EVIDENCE_GATE_METABASE_URL` | Metabase instance URL |
| `EVIDENCE_GATE_METABASE_USERNAME` | Metabase email |
| `EVIDENCE_GATE_METABASE_PASSWORD` | Metabase password |

When credentials are not set, connectors run in **fixture mode** (return synthetic data for development/testing).

## Development

```bash
make test            # Run all 214 tests
make test-boundary   # Run 28 boundary tests
make lint            # Syntax + import check

# Run a single test file
uv run --package evidence-gate pytest evidence_gate/tests/test_log_redactor.py -v

# Lint with ruff (not installed by default; uvx runs it on demand)
uvx ruff check evidence_gate
```

## Installing the skill only

If you want to drop the **Debug Jira** skill into another Claude Code project that already has access to a running `evidence_gate` MCP server — without cloning this whole repo into that project — copy `.claude/skills/debug-jira/` into your target. The skill is 22 static files (SKILL.md, prompts, references, schemas, templates); there is no code to compile.

**Prerequisites**

- Claude Code (or any agent runtime that loads `.claude/skills/`).
- A reachable `evidence_gate` MCP server. The skill cannot function without it — every workflow step calls one of its tools (`start_debugging_session`, `create_quickwit_evidence_request`, …).
- *Optional:* a `code-review-graph` MCP server for code scanning. The skill works without it, but several prompts assume it is available.

If you have no `evidence_gate` server running anywhere, install this whole repo instead — see [Quick Start](#quick-start).

**Choose a scope**

| Scope | Path | Available in |
|-------|------|--------------|
| User | `~/.claude/skills/debug-jira/` | every Claude Code project for your user |
| Project | `<your-project>/.claude/skills/debug-jira/` | one project only |

**Copy the skill**

From a clone of this repo:

```bash
# user scope
mkdir -p ~/.claude/skills
cp -r /path/to/debb/.claude/skills/debug-jira ~/.claude/skills/

# OR project scope
mkdir -p /path/to/your-project/.claude/skills
cp -r /path/to/debb/.claude/skills/debug-jira /path/to/your-project/.claude/skills/
```

Or sparse-checkout from GitHub (no full clone):

```bash
DEST=~/.claude/skills            # or <your-project>/.claude/skills
mkdir -p "$DEST" && cd "$DEST"
git clone --depth 1 --filter=blob:none --sparse <REPO-URL> debb-tmp
git -C debb-tmp sparse-checkout set .claude/skills/debug-jira
mv debb-tmp/.claude/skills/debug-jira .
rm -rf debb-tmp
```

**Register `evidence_gate` in the target project's MCP config**

The skill calls MCP tools by name — they only resolve if a server registered as exactly `evidence_gate` is running. Add it to the target project's `.mcp.json` (or `~/.claude.json` for user scope). When pointing at a local checkout of this repo from a *different* working directory, you must include `--directory`:

```jsonc
{
  "mcpServers": {
    "evidence_gate": {
      "command": "uv",
      "args": [
        "run", "--package", "evidence-gate",
        "--directory", "/absolute/path/to/debb",
        "python", "-m", "evidence_gate.main"
      ],
      "type": "stdio"
    }
  }
}
```

For a remote/shared instance, use whatever stdio bridge your team provides (e.g. `ssh user@host -- /opt/evidence_gate/run.sh`); the registered name must still be `evidence_gate`.

**Verify**

1. Restart Claude Code (or run `/mcp` and reconnect).
2. `/mcp` should list `evidence_gate` as `connected`.
3. Ask Claude Code *“Debug Jira ticket BUG-123.”* The skill should auto-trigger and its first action should be `start_debugging_session`.

If the tool call fails, the most common causes are: server not running, registered under a different name, or missing `EVIDENCE_GATE_*` env vars — check the `evidence_gate` server's logs.

**Update / uninstall**

```bash
# update: re-run the copy command — cp -r overwrites
# uninstall:
rm -rf ~/.claude/skills/debug-jira                     # user scope
rm -rf /path/to/your-project/.claude/skills/debug-jira # project scope
```

Remove the `evidence_gate` entry from the target's MCP config when no longer needed.

## License

Private.
