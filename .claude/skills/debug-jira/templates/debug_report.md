# Debug Report — {{ticket_id}}

**Session**: {{evidence_session_id}} · **Generated**: {{timestamp}} · **Service**: {{primary_service}}

## Summary

- **Symptom**: {{symptom_one_line}}
- **Scope**: {{scope_one_line}}
- **When**: {{when_one_line}}

<!-- Three bullets. One line each. No restatement of the ticket. -->

## Root Cause (most likely)

1. **{{step_1_title}}** — {{step_1_one_liner}} · {{step_1_citation}}
2. **{{step_2_title}}** — {{step_2_one_liner}} · {{step_2_citation}}
3. **{{step_3_title}}** — {{step_3_one_liner}} · {{step_3_citation}}
4. **{{step_4_title}}** — {{user_visible_result}} · {{step_4_citation}}

<!--
Ordered list, one step per line. Each step is the *next* link in the causal chain:
trigger → state read → branch taken → user-visible result. Max ~15 words per step.
Each step ends with `· <citation>`:
  - `<EVID>:Lnn` (line N = hit N in masked_data.hits)
  - `path:Lnn` (with `@commit` if not current master)
  - `git@<sha>` for git-history claims
Use 3–5 steps. No paragraphs. No "in summary" lines.
-->

**Confidence**: {{confidence}} — {{confidence_rationale}}
<!-- One sentence. Name converging streams + residual gap. -->

## Evidence

| Evidence | Plan | Source | Finding |
|----------|------|--------|---------|
{{evidence_table}}
<!-- One row per evidence ID. "Finding" is one line: what the evidence proved or ruled out. -->

## Hypotheses

| # | Hypothesis | Verdict | Reason |
|---|------------|---------|--------|
{{hypothesis_table}}
<!--
Verdict: `supported` | `rejected`.
Reason is one line with a citation. Do not split into Considered+Rejected sections.
-->

## Verification Steps

1. {{step_1}}
2. {{step_2}}
3. {{step_3}}
<!-- Numbered list. Each step independently checkable by the engineer. One line each. -->

## Fix Direction

- {{fix_bullet_1}}
  - Risk: {{fix_risk_1}}
- {{fix_bullet_2}}
  - Risk: {{fix_risk_2}}

<!--
OMIT this section entirely if no fix is being proposed (e.g. fix already shipped).
If included: ≤3 bullets. Risks as a sub-bullet under the relevant bullet, not a separate section.
-->

## References

- **Code**: {{code_refs}}
- **Audits**: {{audit_refs}}
- **Service map**: {{service_map_path}}
- **Jira**: `debug_reports/<TICKET_ID>_<TRACE_ID>/jira/sanitized_ticket.json`
- **Repos considered**: `debug_reports/<TICKET_ID>_<TRACE_ID>/repos/list_repos.json` · selection: `debug_reports/<TICKET_ID>_<TRACE_ID>/repos/candidates.md`
- **Per-EREQ chain** (one entry per accepted Quickwit/Metabase plan):
  `debug_reports/<TICKET_ID>_<TRACE_ID>/plans/<EREQ>.json` → `translations/<EREQ>.json` → `executions/<EREQ>.json` → `evidence/<EVID>.jsonl`
{{optional_refs}}
<!--
Bulleted list. All paths must be the in-session artifact locations so a reviewer
can re-trace the chain from one folder. Use `optional_refs` for companion
sessions or follow-up plan IDs. Do not duplicate evidence IDs or plan IDs
already in the Evidence table.
-->

