# TRACE-Net Table Exact-Search Smoke v1

Local-only smoke search over `trace_net_table_exact_search_adapter_v1` artifacts.

Purpose:

- prove the generated table exact-search JSONL can retrieve known table values;
- avoid touching live OpenSearch until local retrieval behavior is verified;
- preserve TRACE-Net authority boundaries: results are retrieval-only and cannot answer or prove claims.

Inputs:

- `local_data/organization/trace_net/table_exact_search_adapter/trace_net_table_exact_search_adapter_v1.json`

Outputs:

- `trace_net_table_exact_search_smoke_v1.json`
- `trace_net_table_exact_search_smoke_results_v1.jsonl`
- `trace_net_table_exact_search_smoke_v1_inspect.md`

Safety contract:

- no answer permission;
- no direct-answer capability;
- no claim-proof capability;
- no source-truth mutation;
- no Postgres, Qdrant, OpenSearch, or OpenSearch-upload writes.
