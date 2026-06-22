# TRACE-Net Table Hybrid Retrieval Bridge v1

Local-only bridge from table exact-search artifacts into hybrid retrieval ranking signals.

Inputs:

- `table_exact_search_adapter/trace_net_table_exact_search_adapter_v1.json`
- `table_exact_search_smoke/trace_net_table_exact_search_smoke_v1.json`

Outputs:

- `trace_net_table_hybrid_retrieval_bridge_v1.json`
- `trace_net_table_hybrid_retrieval_bridge_records_v1.jsonl`
- `trace_net_table_hybrid_retrieval_bridge_query_groups_v1.jsonl`
- `trace_net_table_hybrid_retrieval_bridge_v1_inspect.md`

Safety contract:

- table records are retrieval/ranking signals only
- no answer permission
- no claim proof
- no source-truth mutation
- no Postgres, Qdrant, OpenSearch, or upload writes
