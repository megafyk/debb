# Debug Report — {{ticket_id}}

**Session**: {{evidence_session_id}} · **Generated**: {{timestamp}} · **Service**: {{primary_service}}

## Summary

{{summary}}
<!-- ≤3 sentences: symptom, scope, when. No restatement of the ticket comments. -->

## Root Cause (most likely)

{{most_likely_root_cause}}
<!--
≤6 sentences. State: trigger → faulty branch → user-visible result.
Cite code as `path:Lnn` (with the commit if not current master).
Cite evidence as `<EVID>:Lnn` (line N = hit N in masked_data.hits).
Do not repeat the summary. Do not restate what each hypothesis was.
-->

**Confidence**: {{confidence}} — {{confidence_rationale}}
<!-- One sentence. Name the converging streams, then name the residual gap. -->

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

{{verification_steps}}
<!-- Numbered list. Each step independently checkable by the engineer. -->

## Fix Direction

{{suggested_fix}}
<!--
OMIT this section entirely if no fix is being proposed (e.g. fix already shipped).
If included: ≤3 bullets. Risks as sub-bullets under the relevant bullet, not a separate section.
-->

## References

- **Code**: {{code_refs}}
- **Audits**: {{audit_refs}}
- **Service map**: {{service_map_path}}
{{optional_refs}}
<!-- Use `optional_refs` for companion sessions or follow-up plan IDs. Do not duplicate evidence IDs or plan IDs already in the Evidence table. -->
