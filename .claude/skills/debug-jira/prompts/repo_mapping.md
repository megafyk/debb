# Repository Mapping Prompt

Using the triage summary and sanitized ticket context, build a service_repo_map.

For each candidate service:

1. Identify the repository path.
2. Read AGENTS.md or CLAUDE.md from the repository root.
3. Check if code-review-graph is available (`graph-status`).
4. If graph is available, use `semantic_search_nodes` to find relevant functions/classes.
5. If graph is not available, use Grep/Glob to find relevant code.
6. Record: suspected code paths, functions, log fields, DB entities, SQL references.

Output the service_repo_map following the schema in `schemas/service_repo_map.schema.json`.

Do not include raw sensitive values. Use only secure value refs from the evidence session.
