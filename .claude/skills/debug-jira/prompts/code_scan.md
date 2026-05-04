# Code Scan Prompt

For each service in the service_repo_map, perform a targeted code scan.

Priority order:
1. Use code-review-graph tools if available (semantic_search_nodes, query_graph callers_of/callees_of/tests_for).
2. Fall back to Grep/Glob/Read only if graph unavailable.

Extract:
- Error handling paths and error codes
- Log statements and their fields
- Database queries and entity references
- API endpoints and their handlers
- Input validation and normalization logic
- Related test files

Record all findings in the service_repo_map entry for each service.
