# TRACE-Net Table Route Value Audit v1

Audits normalized table-route values before they become retrieval/search-ready evidence. The audit does not write to Postgres, Qdrant, OpenSearch, or source-truth artifacts.

## Inputs

- `local_data/organization/trace_net/table_route_value_normalizer/trace_net_table_route_value_normalizer_v1.json`

## Outputs

Under `local_data/organization/trace_net/table_route_value_audit/`:

- `trace_net_table_route_value_audit_v1.json`
- `trace_net_table_route_value_audit_v1_records.jsonl`
- `trace_net_table_route_search_ready_values_v1.jsonl`
- `trace_net_table_route_value_audit_v1_summary.json`
- `trace_net_table_route_value_audit_v1_quality.json`
- `trace_net_table_route_value_audit_v1_manifest.json`

## Behavior

The audit separates normalized table values into:

- search-ready evidence candidates, such as covered part numbers, manual page references, IPL part numbers, quantities/items, and IPL text;
- context-only values, such as LEP/part-list/IPL header or title context;
- review-required table records, such as unknown templates, high-context LIST OF EFFECTIVE PAGES tables, duplicates, or missing template-required fields.

## Safety contract

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- no claim-proof authority
