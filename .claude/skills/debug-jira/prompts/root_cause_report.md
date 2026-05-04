# Root Cause Report Prompt

Synthesize all findings into a debug report following `templates/debug_report.md`.

Requirements:
- State the most likely root cause clearly.
- Assign confidence: low, medium, or high with rationale.
- Cite every evidence ID, query plan ID, code path, and audit ref.
- List hypotheses considered and why alternatives were rejected.
- Include specific engineer verification steps.
- Suggest a fix direction with risks.
- Never claim the AI proved the root cause — use "most likely" language.
- Never include raw sensitive values.
