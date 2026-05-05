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
| `submit_debug_report` | Submit final root-cause report |

## Quick Start

```bash
# Prerequisites: Python 3.12+, uv
uv sync

# Copy and configure environment
cp .env.example .env
# Edit .env with your Jira/Quickwit/Metabase credentials

# Run tests (uses fixture mode — no credentials needed)
make test

# Run boundary tests only
make test-boundary
```

## Project Structure

```
.claude/skills/debug-jira/   # Skill definition (SKILL.md, schemas, prompts, templates)
evidence_gate/
  evidence_gate/
    app/                     # Config, FastAPI app
    contracts/               # Pydantic domain models
    connectors/              # Jira, Quickwit, Metabase (live + fixture mode)
    redaction/               # PII extraction, log/DB redaction
    request_services/        # Query validation pipeline, executor, report reviewer
    sessions/                # Session + sensitive value stores
    storage/                 # JSON/JSONL persistence
    audit/                   # Append-only audit log
    mcp_server/              # FastMCP stdio server (7 tools)
  tests/                     # 192 tests
    boundary/                # 26 trust-boundary tests
docs/
  debugging_system_implementation_plan.md
  log.md                     # Changelog
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
make test            # Run all 192 tests
make test-boundary   # Run 26 boundary tests
make lint            # Syntax + import check
```

## License

Private.
