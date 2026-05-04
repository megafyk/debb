# Query Plan Rules

## Quickwit plans must include
- service name
- index_hint matching a known log index
- time_window with start and end (prefer narrow windows)
- at least one filter
- fields_requested (never request all fields)
- max_hits <= 500
- output_profile name

## Metabase plans must include
- service name
- entity name
- query_intent describing what diagnostic facts are needed
- facts_requested list
- output_profile name

## Plans must not include
- Raw sensitive values (use value_ref instead)
- SELECT * queries
- Unbounded time windows
- Missing service context
