# Report Reviewer Prompt

Review the debug report for quality and safety.

Check:
1. **No raw sensitive values** — no phone numbers, emails, names, account IDs, credentials, tokens.
2. **Evidence citations** — every claim cites an evidence ID or code path.
3. **Confidence calibration** — confidence level matches evidence strength.
4. **Verification steps** — actionable steps an engineer can follow.
5. **No overstatement** — uses "most likely", not "proven" or "confirmed".
6. **Complete** — all sections from the template are filled.

If issues found, list them. Do not auto-fix — flag for the engineer.
