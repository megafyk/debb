# Report Quality Rules

## Required sections
Every debug report must include all sections from `templates/debug_report.md`.

## Citation requirements
- Every factual claim must cite an evidence ID, code path, or audit ref.
- Prefer line-precise citations using the masked package's `evidence_file`:
  cite individual hits as `<evidence_file.path>:L<line_number>` (e.g.
  `debug_reports/BUG-123_4bf9.../evidence/EVID-abc.jsonl:L3`). Line N in
  the JSONL corresponds to hit N (1-indexed) in `masked_data.hits`.
- Hypotheses must reference the evidence that supports or refutes them.

## Confidence calibration
- **High**: Multiple independent evidence sources converge on the same cause.
- **Medium**: Code analysis and one evidence source align, but gaps remain.
- **Low**: Hypothesis is consistent with available evidence but unverified.

## Language rules
- Use "most likely root cause", not "the root cause" or "proven cause".
- Use "evidence suggests", not "evidence proves".
- Always include "Required Engineer Verification Steps".

## Safety checks before submission
- No raw phone numbers, emails, names, account IDs
- No credentials, tokens, auth headers
- No raw log lines or DB rows
- All evidence IDs are valid references
