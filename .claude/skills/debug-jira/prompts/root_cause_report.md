# Root Cause Report Prompt

Synthesize findings into a debug report at `debug_reports/<TICKET_ID>_<TRACE_ID>/debug_report.md`,
following `templates/debug_report.md` exactly.

## Output rules

- **Be concise.** Target ≤120 lines for the rendered Markdown. Engineer reads this to act, not to learn.
- **No redundancy.** Each fact appears once. Do not repeat evidence IDs, plan IDs, or code paths across sections.
- **No filler sections.** Omit `Fix Direction` if no fix is proposed. Omit `optional_refs` if empty. Do not add sections beyond the template.
- **Cite at the point of claim.** Every factual claim gets an inline citation (`<EVID>:Lnn` or `path:Lnn`) — not a "see References" pointer.
- **Hypotheses go in one table.** Do not split into Considered + Rejected.
- **Prose only where structure can't carry the meaning.** Use bullets and tables for the rest.

## Content rules

- State the most likely root cause clearly using "most likely" / "evidence suggests" language — never "proven".
- Confidence: `low` | `medium` | `high`. One-sentence rationale naming converging streams and residual gap.
- Verification steps: numbered, each independently checkable.
- Never include raw sensitive values. Never claim the AI proved the root cause.
- Required schema fields (`evidence_ids`, `audit_refs`, `verification_steps`, etc.) must still be present in the JSON submitted to `submit_debug_report`, even when their dedicated Markdown section is folded into a table or references list.
