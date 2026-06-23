# TRACE-Net E2E Hybrid Retrieval Runtime v1

This module is the first retrieval runtime step in the end-to-end TRACE-Net path.
It consumes `trace_net_e2e_query_input_v1.json` and the table hybrid retrieval
bridge, then emits ranked retrieval groups.

## Contract

- Retrieval/ranking only until the final TRACE-Net gate.
- No answer authority.
- No claim proof authority.
- No source-truth mutation.
- No Postgres, Qdrant, OpenSearch, or upload writes.

## Inputs

- `local_data/organization/trace_net/e2e_query_input/trace_net_e2e_query_input_v1.json`
- `local_data/organization/trace_net/table_hybrid_retrieval_bridge/trace_net_table_hybrid_retrieval_bridge_v1.json`

## Outputs

- `trace_net_e2e_hybrid_retrieval_runtime_v1.json`
- `trace_net_e2e_hybrid_retrieval_groups_v1.jsonl`
- `trace_net_e2e_hybrid_retrieval_runtime_v1_quality.json`
- `trace_net_e2e_hybrid_retrieval_runtime_v1_inspect.md`

## Why this exists

The query-input harness plans the query, but it does not retrieve. This module
is the next bridge: it turns those planned queries into concrete ranked local
retrieval groups that can be consumed by the next context-pack builder.
