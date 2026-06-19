# Source types

The registry currently supports three source types. Each has a typed `metadata` schema; the helper script rejects sources whose metadata doesn't match.

## quickwit

Quickwit is the log search backend used by debug-jira to plan log queries.

| Field | Required | Description | Where to find it |
|---|---|---|---|
| `id` | yes | Numeric Quickwit index ID. | Quickwit admin UI → "Indexes" → numeric column. |
| `uid` | yes | Stable index UID used in URLs and API calls. | Quickwit admin UI → index detail page. |
| `index_pattern` | no | Human-friendly pattern (e.g. `payments-app-*`). | Documentation only; not used by tooling. |

**Example:**
```json
{ "name": "quickwit", "metadata": { "id": 59, "uid": "cditnbnbvzugwb" } }
```

## metabase

Metabase is the BI tool used by debug-jira to plan SQL queries against application databases. The Metabase API (`POST /api/dataset`) takes the **numeric** database ID — see `docs/metabase_query` for the canonical curl example.

| Field | Required | Description | Where to find it |
|---|---|---|---|
| `database` | yes | Metabase database name as shown in the admin UI (human label, used for matching/audit). | Metabase → Admin → Databases. |
| `database_id` | yes | Numeric Metabase database ID — this is the value sent as `database` in `/api/dataset` calls. | URL when viewing the DB in Metabase admin (`/admin/databases/<id>`). |
| `database_type` | no | Engine (e.g. `mariadb`, `mysql`, `postgres`). Picks the dialect-specific pre-query recipe at `docs/metabase_<database_type>_pre_query` so the planner can introspect indexes/columns before writing optimized SQL. | Metabase → Admin → Databases → engine column. |
| `schema` | no | Schema name. Used to qualify table refs as `schema.table` in SQL (e.g. `cdcn_log_central.log_central`). | Database introspection. |
| `tables` | no | Allow-list of tables the service may query in this database/schema. | Service code / DB introspection. |

**Example:**
```json
{
  "name": "metabase",
  "metadata": {
    "database": "View_cdcn_auth_service_prod",
    "database_id": 6,
    "database_type": "mariadb",
    "schema": "cdcn_auth_service",
    "tables": ["users", "tokens"]
  }
}
```

**Consumer contract:** debug-jira reads `database_id` + `schema` from the matching source and copies them into the `MetabaseQueryPlan` it submits to evidence_gate. evidence_gate's connector then puts `database_id` in the `database` field of the `/api/dataset` body and substitutes the `{schema}` placeholder in the plan's agent-authored `sql_candidate` (`schema` must be a bare SQL identifier).

## prometheus

Prometheus exposes service metrics. Used when debug-jira needs to correlate latency/error spikes.

| Field | Required | Description | Where to find it |
|---|---|---|---|
| `job` | yes | Prometheus `job` label that scrapes this service. | Prometheus targets page or Grafana dashboard. |
| `namespace` | no | Kubernetes namespace or logical grouping. | Deployment manifest. |
| `metric_prefix` | no | Common prefix for service-specific metrics. | Service code or metrics docs. |

**Example:**
```json
{ "name": "prometheus", "metadata": { "job": "payments-api", "namespace": "payments" } }
```

## Adding a new source type

1. Add `schemas/source_<name>.schema.json`.
2. Update the `name` enum and `oneOf` in `schemas/registry_entry.schema.json`.
3. Add the new type to the `sources` map in `_entry_schema_with_inline_refs` in `scripts/registry.py` so the script inlines the right metadata schema.
4. Document the new fields here.
5. Update `references/debug_jira_integration.md` if debug-jira should consume the new type.
