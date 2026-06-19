# evidence_gate MCP Tools Reference

## Available Tools

### start_debugging_session
Start a new debugging session for a Jira ticket.
- **Input**: `ticket_id_or_url` (string), `trace_id` (string, optional), `idempotency_key` (string, optional)
- **Output**: EvidenceSessionContext (session ID, sanitized ticket, sensitive refs, audit refs)

### get_sanitized_jira_ticket
Get sanitized Jira ticket context for an existing session.
- **Input**: `evidence_session_id` (string)
- **Output**: SanitizedTicketContext

### create_quickwit_evidence_request
Submit a Quickwit query plan for execution.
- **Input**: QuickwitQueryPlan object
- **Output**: Evidence request ID and status

### create_metabase_evidence_request
Submit a Metabase query plan for execution. The plan carries an agent-authored
`sql_candidate` (a native query) plus `params`; there is no template registry.
evidence_gate gates it (rejects `SELECT *`, mutating statements, and any `schema`
that is not a bare identifier) and caps results at 500 rows.
- **Input**: MetabaseQueryPlan object
- **Output**: Evidence request ID and status

### get_evidence_request_status
Check the status of an evidence request.
- **Input**: `evidence_request_id` (string)
- **Output**: Current state, audit ref

### get_masked_evidence_package
Retrieve the masked evidence package for a completed request.
- **Input**: `evidence_id` (string)
- **Output**: MaskedEvidencePackage. For Quickwit packages, `masked_data.correlation_ids` is a `{field: [unique_values]}` map covering `contextMap.traceId`, `contextMap.correlationID`, `contextMap.requestID`, `requestID`, `sessionID` — pick the first non-empty key to drive the next-stage correlation query.

### submit_debug_report
Submit a completed debug report.
- **Input**: DebugReport object
- **Output**: Report ID, audit ref
