# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## Project Conventions

- **`docs/log.md` is the project's ADR (Architecture Decision Record).** Record architectural decisions there in ADR format (Context, Decision, Consequences). Do not treat it as a freeform changelog or activity log. Read existing entries first to match the established format.

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes_tool` or `query_graph_tool` instead of Grep
- **Understanding impact**: `get_impact_radius_tool` instead of manually tracing imports
- **Code review**: `detect_changes_tool` + `get_review_context_tool` instead of reading entire files
- **Finding relationships**: `query_graph_tool` with callers_of / callees_of / imports_of / importers_of / tests_for / file_summary / children_of / inheritors_of
- **Architecture questions**: `get_architecture_overview_tool` + `list_communities_tool`
- **Cross-repo lookups**: `cross_repo_search_tool` (do not use `list_repos_tool` for repo enumeration in debug-jira — that comes from `.claude/skills/debug-repo/registry.json`)

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools (subset — full catalogue: 29 tools)

Names below are the upstream tool names. From MCP they are addressed as
`mcp__code-review-graph__<name>`. See
`.claude/skills/debug-jira/references/code_review_graph.md` for the complete
list and the picking guide.

| Tool | Use when |
|------|----------|
| `semantic_search_nodes_tool` | Finding functions/classes/files by name or meaning — start here |
| `query_graph_tool` | Tracing callers, callees, imports, tests, file_summary, children_of, inheritors_of |
| `get_minimal_context_tool` | Need a ~100-token sketch of a node's neighbourhood before reading source |
| `get_review_context_tool` | Token-efficient source snippets across changed files |
| `get_impact_radius_tool` | Blast radius of a change |
| `get_affected_flows_tool` | Which execution paths are impacted by a change |
| `traverse_graph_tool` | BFS/DFS from a node with a token budget |
| `detect_changes_tool` | Risk-scored change-impact analysis for code review |
| `get_architecture_overview_tool` / `list_communities_tool` / `get_community_tool` | Architectural orientation |
| `get_hub_nodes_tool` / `get_bridge_nodes_tool` | Find hotspots & chokepoints |
| `find_large_functions_tool` | Locate oversized functions for refactoring |
| `refactor_tool` / `apply_refactor_tool` | Plan and apply renames / dead-code removals |
| `list_graph_stats_tool` | Verify the graph is built and fresh |
| `cross_repo_search_tool` | Search across all CRG-registered repos |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes_tool` for code review.
3. Use `get_affected_flows_tool` to understand impact.
4. Use `query_graph_tool` `pattern="tests_for"` to check coverage.
