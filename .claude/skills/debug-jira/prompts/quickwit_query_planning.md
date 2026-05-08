# Quickwit Query Planning Prompt

Quickwit logs are read through Grafana's `/ds/query` proxy. Plans mirror Grafana's
`MetricRequest` at the top level: `from`, `to`, and a single `queries[0]` entry
identified by `datasource_uid`.

## Required plan fields

- `service` — the service name being investigated.
- `datasource_uid` — the Grafana data source UID that proxies to the Quickwit index for this service.
- `from`, `to` — ISO 8601 strings (preferred), epoch ms, or Grafana relative (`now-1h`, `now`). Prefer narrow windows; bounds_checker narrows windows over 24h.
- `ref_id` — optional, defaults to `"A"`.
- `max_data_points`, `interval_ms` — optional Grafana panel hints.
- `filters` — at least one `QueryFilter`. Use `matches_sensitive_ref` (with `value_ref`) for sensitive values; never inline raw PII.
- `fields_requested` — see "Choosing fields_requested" below.
- `max_hits` — `<=` 500. bounds_checker narrows higher values.
- `query_intent` — what diagnostic signal the plan is trying to surface.
- `output_profile` — name of the masked output shape expected.

## Choosing `fields_requested`

`fields_requested` is selected deterministically from the prior code-scan
output. There is exactly one candidate pool: the `log_fields` recorded in the
`service_repo_map` entry for the target service (see `prompts/code_scan.md`).
Nothing outside that pool is legal.

Selection rule (apply in order):

1. **Anchor on the code scan.** Load
   `service_repo_map.services[].log_fields` for the target service. This is
   the candidate pool. If it is empty, stop — either rerun the code scan with
   broader `suspected_code_paths`, or pause and ask the user (per SKILL.md
   step 8) which logger calls cover the failure path. Do not invent fields.
2. **Prefer fields on the failure path.** Keep fields emitted by the
   `suspected_code_paths` / `suspected_functions` for this ticket. Those are
   the ones the failing request actually walks past.
3. **Cross-check with the Jira ticket.** Promote pool fields that match
   symptom keywords, error codes, or correlation identifiers named/implied in
   the sanitized ticket (e.g. ticket says "trace_id" → keep `trace_id` if
   it is in `log_fields`).
4. **Drop everything else.** A field that is not in `log_fields` cannot be
   requested — even if the ticket names it. The connector emits the empty
   result and you waste a replan attempt. A ticket-named field absent from
   the pool is a code-scan gap, not a Quickwit input.

Record each chosen field's origin (which `code_paths` entry emits it) in the
plan's `code_paths` so reviewers can trace the selection back to source.

## Replan on zero hits

The connector returns a `QuickwitQueryResult` with `is_valuable=false` and
`reason="zero_hits"` when the query lands no records. The masked package will
also report `hit_count == 0`. When that happens:

1. Note that the current plan was unproductive.
2. Revise *one* of: the time window (widen by a small factor), the filter set
   (relax over-tight equality, drop a filter that may not match), or the
   `fields_requested`/`datasource_uid` (mismatched index).
3. Resubmit through `create_quickwit_evidence_request` with the revised plan.
4. Stop after a reasonable number of attempts (≤3); if still empty, surface
   the gap in the debug report rather than burning more queries.

Each replan is a separate evidence request — never mutate a submitted plan.

Submit plans to evidence_gate via `create_quickwit_evidence_request`.

The plan is a planning artifact. evidence_gate may reject, narrow, or modify it.
