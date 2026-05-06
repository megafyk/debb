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
.claude/skills/debug-jira/   # Skill definition (SKILL.md, schemas, prompts, templates)
evidence_gate/
  evidence_gate/
    main.py                  # MCP server entry point
    config.py                # Settings (EVIDENCE_GATE_* env vars)
    contracts.py             # Pydantic domain models
    audit_logger.py          # Append-only audit log
    connectors/              # Jira, Quickwit, Metabase (live + fixture mode)
    redaction/               # PII extraction, log/DB/Jira redaction, leakage patterns
    request_services/        # Schema/safety/bounds checks, executor, report reviewer
    storage/                 # Session, sensitive-value, request, raw + masked stores
    mcp_server/              # MCP stdio server, tool registration (8 tools)
  tests/                     # 184 tests
    boundary/                # 28 trust-boundary tests
docs/
  debugging_system_implementation_plan.md
  log.md                     # ADR (architecture decision record)
```

## How It Works

1. Engineer asks the AI agent to debug a Jira ticket
2. Agent invokes the **Debug Jira** skill
3. Skill calls `start_debugging_session` → gets a session ID
4. Skill calls `get_sanitized_jira_ticket` → gets PII-redacted ticket context
5. Agent builds query plans (log searches, DB lookups) grounded in code
6. Skill submits plans → evidence_gate validates (schema, safety, bounds)
7. evidence_gate executes against Quickwit/Metabase, redacts results
8. Agent receives only masked evidence packages
9. Agent writes a debug report citing evidence IDs and code paths
10. Skill submits report → programmatic review checks for leakage

## Configuration

All settings use the `EVIDENCE_GATE_` prefix:

| Variable | Purpose |
|----------|---------|
| `EVIDENCE_GATE_JIRA_BASE_URL` | Jira Cloud instance URL |
| `EVIDENCE_GATE_JIRA_USERNAME` | Atlassian email |
| `EVIDENCE_GATE_JIRA_PASSWORD` | Atlassian API token |
| `EVIDENCE_GATE_QUICKWIT_URL` | Quickwit search endpoint |
| `EVIDENCE_GATE_QUICKWIT_USERNAME` | Quickwit Basic Auth user |
| `EVIDENCE_GATE_QUICKWIT_PASSWORD` | Quickwit Basic Auth password |
| `EVIDENCE_GATE_METABASE_URL` | Metabase instance URL |
| `EVIDENCE_GATE_METABASE_USERNAME` | Metabase email |
| `EVIDENCE_GATE_METABASE_PASSWORD` | Metabase password |

When credentials are not set, connectors run in **fixture mode** (return synthetic data for development/testing).

## Development

```bash
make test            # Run all 184 tests
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
