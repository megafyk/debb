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

Metabase is the BI tool used by debug-jira to plan SQL queries against application databases.

| Field | Required | Description | Where to find it |
|---|---|---|---|
| `database` | yes | Metabase database name as shown in the admin UI. | Metabase → Admin → Databases. |
| `database_id` | no | Numeric ID for API calls. | URL when viewing the DB in Metabase admin. |
| `schema` | no | Schema name (when DB has multiple schemas). | Database introspection. |

**Example:**
```json
{ "name": "metabase", "metadata": { "database": "metabase_db" } }
```

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
2. Add the type name to `VALID_SOURCE_NAMES` and the `_entry_schema_with_inline_refs` mapping in `scripts/registry.py`.
3. Update the `name` enum and `oneOf` in `schemas/registry_entry.schema.json`.
4. Document the new fields here.
5. Update `references/debug_jira_integration.md` if debug-jira should consume the new type.
