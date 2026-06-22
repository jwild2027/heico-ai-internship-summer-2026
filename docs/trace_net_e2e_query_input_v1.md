# TRACE-Net E2E Query Input v1

This module is the first end-to-end runtime harness piece. It accepts user queries and emits a safe, stable query-input artifact for the later hybrid retrieval runtime.

It does **not** retrieve, answer, mutate source truth, write to Postgres, write to Qdrant, write/upload to OpenSearch, or grant answer authority.

## Outputs

`local_data/organization/trace_net/e2e_query_input/trace_net_e2e_query_input_v1.json`

`local_data/organization/trace_net/e2e_query_input/trace_net_e2e_query_input_records_v1.jsonl`

`local_data/organization/trace_net/e2e_query_input/trace_net_e2e_query_input_v1_inspect.md`

`local_data/organization/trace_net/e2e_query_input/trace_net_e2e_query_input_v1_quality.json`

## Safety contract

Each query record is retrieval-only:

- `answer_permission=false`
- `can_answer_directly=false`
- `can_prove_claims=false`
- `source_truth_mutation_allowed=false`
- `postgres_write_attempt=false`
- `qdrant_write_attempt=false`
- `opensearch_write_attempt=false`
- `opensearch_upload_attempt=false`

## Next module

The next module should consume this artifact and run the local hybrid retrieval runtime: Qdrant/page profiles, exact-search documents, table bridge signals, graph/source hints, and route constraints.
