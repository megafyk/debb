# code-review-graph Usage

## When available
Check with `graph-status`. If the graph is built, prefer graph tools over Grep/Glob.

## Key tools for debugging

### semantic_search_nodes
Find functions/classes by keyword. Use for initial discovery.
```
semantic_search_nodes("login failure phone normalization")
```

### query_graph
Trace relationships:
- `callers_of`: who calls this function
- `callees_of`: what this function calls
- `tests_for`: test coverage
- `imports_of`: module dependencies

### get_impact_radius
Understand blast radius of a suspected buggy function.

### get_affected_flows
Find execution paths through a suspected code area.

## Recording graph usage
Record all graph queries in the service_repo_map `graph_queries_used` field.
