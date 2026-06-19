# Quickwit Query Planning Prompt

Quickwit logs are read through Grafana's `/ds/query` proxy. Plans mirror Grafana's
`MetricRequest` at the top level: `from`, `to`, and a single `queries[0]` entry
identified by `datasource_uid`.

**Scope:** the strategy below is Quickwit-only. It targets the request
journey across log emitters and depends on log-shaped fields (`message`,
`level`, `contextMap.*`, kubernetes labels). Metabase plans run an agent-authored
`sql_candidate` (native query) against application databases — they don't have a
journey to correlate, so do not port any of this to `prompts/metabase_query_planning.md`.

## Three-stage strategy

A user-reported bug rarely fits in one query. Submit a separate evidence
request per stage — never mutate a submitted plan.

### Stage 1 — Identify the failing request

Goal: find the masked package's first hit so you can extract its trace ID.

Filter on:
- `kubernetes.namespace_name` = environment in scope (e.g. `production`).
- `kubernetes.labels.app_kubernetes_io/instance` = `<env>-<service>` (the
  registry's `connection[].environment` + service name).
- `level` = `ERROR` (or `WARN` if the symptom is a near-miss).
- `message` `contains` an error literal grepped from the candidate repo's
  `logger.error(...)` call sites in the code-scan step. Never invent a string.
- One filter narrowing to the user's request — typically
  `contextMap.msisdn` `matches_sensitive_ref` `<value_ref>` for masked PII,
  or a non-sensitive correlation hint (order ID, internal user ID) inline.

Request enough fields to read the journey *and* the correlation IDs:
`level`, `message`, `contextMap.traceId`, `contextMap.correlationID`,
`contextMap.requestID`, `requestID`, `sessionID`, `kubernetes.pod_name`,
`duration`.

### Stage 2 — Correlate the full journey

The masked package surfaces every correlation ID found in stage-1 hits under
`masked_data.correlation_ids`, in this priority order:

1. `contextMap.traceId`
2. `contextMap.correlationID`
3. `contextMap.requestID`
4. `requestID`
5. `sessionID`

Pick the first non-empty key and submit stage 2 with:
- `kubernetes.namespace_name` = same environment as stage 1.
- The picked correlation field `=` the picked value.
- **No `level` filter** — INFO/WARN preceding the ERROR is the lead-up you need.
- **No `app_kubernetes_io/instance` filter** — the same trace ID will appear
  in upstream/downstream services; cross-service journey is the point.
- `fields_requested` adds `contextMap.spanId`, `contextMap.parentId`,
  `contextMap.time_start`, and `responseContent` so you can reconstruct the
  call tree and order events.

### Stage 3 — Fallback when stage 2 is empty

If stage 2 returns `total_hits == 0`, drop down the priority list and resubmit
with the next correlation field that had values in stage 1. Cap the chain at
3 attempts total (across stages 2 and 3) per the replan policy below.

If stage 1's `correlation_ids` was empty for *all* fields, that itself is the
finding: the failing path emits no correlation context, surface that gap in
the report rather than burning more queries.

### Stage 4 — Analysis (no further queries)

Walk stage-2 hits ordered by `contextMap.time_start`. Cross-check each
emitter against the candidate repo's `code_paths`. Group by `pod_name` to
distinguish pod-localized failures from fleet-wide ones. Use `duration`
around the failing span to distinguish slow-then-failed (timeout/network)
from fast-and-failed (validation/exception).

## Required plan fields

- `service` — service name being investigated.
- `datasource_uid` — Grafana data source UID for this service's Quickwit
  index. Pull from the registry's `connection[].sources[].metadata.uid`.
- `from`, `to` — ISO 8601 strings (preferred), epoch ms, or Grafana relative
  (`now-1h`, `now`). bounds_checker narrows ISO windows over 24h; epoch ms
  and relative strings pass through unchanged.
- `ref_id` — optional, defaults to `"A"`.
- `max_data_points`, `interval_ms` — optional Grafana panel hints.
- `filters` — at least one. Use `matches_sensitive_ref` (with `value_ref`)
  for sensitive values; never inline raw PII.
- `fields_requested` — see "Choosing fields_requested".
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
2. **Always include the correlation pool.** Whichever of the five
   correlation fields above appear in `log_fields`, include them — that's
   what populates `masked_data.correlation_ids` for stage 2.
3. **Prefer fields on the failure path.** Keep fields emitted by the
   `suspected_code_paths` / `suspected_functions` for this ticket. Those are
   the ones the failing request actually walks past.
4. **Cross-check with the Jira ticket.** Promote pool fields that match
   symptom keywords, error codes, or correlation identifiers named/implied in
   the sanitized ticket.
5. **Drop everything else.** A field that is not in `log_fields` cannot be
   requested — the connector emits nothing for it and you waste a replan
   attempt. A ticket-named field absent from the pool is a code-scan gap,
   not a Quickwit input.

Record each chosen field's origin (which `code_paths` entry emits it) in the
plan's `code_paths` so reviewers can trace the selection back to source.

## Replan on zero hits

The connector returns a `QuickwitQueryResult` with `is_valuable=false` and
`reason="zero_hits"` when the query lands no records, and the masked package
reports `total_hits == 0`. When that happens:

1. Note that the current plan was unproductive.
2. Revise *one* of: the time window (widen by a small factor), the filter
   set (relax over-tight equality, drop a filter that may not match), or the
   `fields_requested`/`datasource_uid` (mismatched index). For stage-2/3
   correlation queries, the natural revision is the next correlation field
   in the priority list.
3. Resubmit through `create_quickwit_evidence_request` with the revised plan.
4. Stop after a reasonable number of attempts (≤3); if still empty, surface
   the gap in the debug report rather than burning more queries.

Each replan is a separate evidence request — never mutate a submitted plan.

Submit plans to evidence_gate via `create_quickwit_evidence_request`.

The plan is a planning artifact. evidence_gate may reject, narrow, or modify it.
