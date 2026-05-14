# Root Cause Report Prompt

Synthesize findings into a debug report at `debug_reports/<TICKET_ID>_<TRACE_ID>/debug_report.md`,
following `templates/debug_report.md` exactly.

## Output rules

- **Bullets and tables only.** Prose paragraphs are not allowed in any section. If a thought
  needs more than one line, split it into separate bullets.
- **One line per bullet.** Soft cap ~25 words. Long lines are a smell — usually two facts that
  should be two bullets.
- **Cite at the point of claim.** Every bullet that asserts a fact ends with `· <citation>`:
  - `<EVID>:Lnn` (line N = hit N in masked_data.hits)
  - `path:Lnn` (with `@<commit>` if not current master)
  - `git@<sha>` for git-history claims
- **Root Cause is an ordered list.** 3–5 numbered steps, each `**Title** — one-liner · citation`.
  The list reads as a causal chain: trigger → state read → branch taken → user-visible result.
- **No redundancy.** Each fact appears once. Do not repeat evidence IDs, plan IDs, or code paths
  across sections.
- **Hypotheses go in one table.** Do not split into Considered + Rejected sections.
- **Target ≤80 lines** for the rendered Markdown.
- **No filler sections.** Omit `Fix Direction` if no fix is proposed. Omit `optional_refs` if empty.
  Do not add sections beyond the template.

## Content rules

- State the most likely root cause using "most likely" / "evidence suggests" language —
  never "proven" or "confirmed".
- Confidence: `low` | `medium` | `high`. One-sentence rationale naming converging streams and
  residual gap.
- Verification steps: numbered, each independently checkable, one line.
- Never include raw sensitive values. Never claim the AI proved the root cause.
- Required schema fields (`evidence_ids`, `audit_refs`, `verification_steps`, etc.) must still be
  present in the JSON submitted to `submit_debug_report`, even when their dedicated Markdown
  section is folded into a table or references list.
