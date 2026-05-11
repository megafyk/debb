# Report Reviewer Prompt

Review the debug report for quality and safety.

Check:
1. **No raw sensitive values** — no phone numbers, emails, names, account IDs, credentials, tokens.
2. **Evidence citations** — every claim cites an evidence ID or code path inline.
3. **Confidence calibration** — confidence level matches evidence strength; rationale is one sentence.
4. **Verification steps** — actionable steps an engineer can follow.
5. **No overstatement** — uses "most likely", not "proven" or "confirmed".
6. **Required sections present** — Summary, Root Cause, Evidence, Hypotheses, Verification Steps, References. `Fix Direction` is optional and may be omitted when no fix is proposed.

If issues found, list them. Do not auto-fix — flag for the engineer.
