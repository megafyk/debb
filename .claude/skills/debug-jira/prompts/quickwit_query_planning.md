# Quickwit Query Planning Prompt

Using the service_repo_map and code scan findings, create QuickwitQueryPlan objects.

Rules:
- Every plan must include: service, index_hint, time_window, filters, fields_requested, max_hits.
- Use log fields discovered from code, not guesses.
- Reference secure value refs for sensitive filter values (use `matches_sensitive_ref` op).
- Keep time windows narrow (prefer hours, not days).
- Limit max_hits to 500 or less.
- Set output_profile to describe the expected masked output format.

Submit plans to evidence_gate via `create_quickwit_evidence_request`.

The plan is a planning artifact. evidence_gate may reject, narrow, or modify it.
