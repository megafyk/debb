# Metabase Query Planning Prompt

Using the service_repo_map and code scan findings, create MetabaseQueryPlan objects.

Rules:
- Every plan must include: service, entity, query_intent, facts_requested.
- Populate `database_id`, `database_type`, and `schema` from the service's registry entry — pick the metabase source whose `schema` and `tables` cover the entity you're querying, and copy that source's `database_id`, `database_type`, and `schema` into the plan. Without `database_id`, evidence_gate will reject the live query.
- **Pre-query before optimizing.** Before writing `sql_candidate`, read `docs/metabase_<database_type>_pre_query` (e.g. `docs/metabase_mariadb_pre_query` when the source's `database_type` is `mariadb`). That file is the canonical recipe for the dialect — it contains the introspection queries to gather indexes, column types, and partitions for the target table(s), plus the optimization rules to apply. Submit those introspection statements as their own metabase plans first (one per `sql_candidate`), then use the returned metadata to write an optimized final `sql_candidate`. Skip the pre-query step only when the same table was already introspected in this evidence session.
- sql_candidate is a planning artifact only — evidence_gate decides what actually runs. When referencing tables, qualify them as `schema.table` (e.g. `cdcn_log_central.log_central`), using the `{schema}` placeholder where the schema is substituted in. `schema` must be a bare identifier — evidence_gate rejects non-identifier values.
- No `SELECT *` or mutating SQL — evidence_gate's safety gate rejects them. Select named columns only.
- Results are capped at 500 rows; prefer aggregates (`GROUP BY`, `COUNT`) or an explicit `LIMIT` over row dumps.
- Use value_ref for sensitive parameters, never raw values.
- Request only the diagnostic facts needed for the hypothesis.
- Set output_profile to describe the expected masked output format.

Submit plans to evidence_gate via `create_metabase_evidence_request`.
