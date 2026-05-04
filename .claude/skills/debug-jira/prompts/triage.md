# Triage Prompt

You have received a sanitized Jira ticket context from evidence_gate.

Analyze the sanitized ticket to determine:

1. **Issue category**: login failure, data inconsistency, performance degradation, error spike, etc.
2. **Affected services**: which services are mentioned in components, labels, description, or comments.
3. **Key identifiers**: secure value refs provided (do NOT attempt to resolve these).
4. **Time window**: when the issue was reported and any timestamps mentioned.
5. **Severity signals**: priority, status, linked incidents.

Output a triage summary with:
- Issue category
- Candidate services to investigate
- Suggested time window for evidence queries
- Key secure value refs to use in query plans
