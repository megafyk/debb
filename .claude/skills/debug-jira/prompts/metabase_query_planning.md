# Metabase Query Planning Prompt

Using the service_repo_map and code scan findings, create MetabaseQueryPlan objects.

Rules:
- Every plan must include: service, entity, query_intent, facts_requested.
- sql_candidate is a planning artifact only — evidence_gate decides what actually runs.
- Use value_ref for sensitive parameters, never raw values.
- Request only the diagnostic facts needed for the hypothesis.
- Set output_profile to describe the expected masked output format.

Submit plans to evidence_gate via `create_metabase_evidence_request`.
