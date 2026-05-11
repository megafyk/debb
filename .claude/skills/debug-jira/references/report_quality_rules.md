# Report Quality Rules

## Structure
- Use the sections in `templates/debug_report.md`, in order.
- Omit `Fix Direction` when no fix is being proposed.
- Do not add sections beyond the template. Do not split one section into two.

## Brevity
- Target ≤120 lines of rendered Markdown. If the report grows past that, cut prose before cutting evidence.
- Each fact appears once. If it belongs in a table, do not also write it in prose.
- One-line cells in tables. If a finding needs more than one line, the prose belongs in `Root Cause`, not in the Evidence row.
- `Confidence` rationale is one sentence — converging streams + residual gap.

## Citations
- Every factual claim must cite an evidence ID, code path, or audit ref **at the point of claim**, not in a trailing References dump.
- Evidence line cites use `<evidence_file.path>:L<line_number>` (line N = hit N in `masked_data.hits`, 1-indexed).
- Code cites use `path:Lnn` for current master, `path:Lnn@<commit>` when pinning to a non-master commit.

## Confidence calibration
- **High**: Multiple independent evidence streams converge on the same cause.
- **Medium**: Code analysis and one evidence source align, but gaps remain.
- **Low**: Hypothesis is consistent with available evidence but unverified.

## Language
- "most likely root cause", not "the root cause" or "proven".
- "evidence suggests", not "evidence proves".
- Always include `Verification Steps`, even when confidence is High.

## Safety
- No raw phone numbers, emails, names, account IDs.
- No credentials, tokens, auth headers.
- No raw log lines or DB rows.
- All evidence IDs are valid references.
