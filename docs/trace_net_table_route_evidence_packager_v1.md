# TRACE-Net table-route evidence packager v1

`trace_net_table_route_evidence_packager_v1` is the next module after the LEP-v4 table value audit. It reads the local `trace_net_table_route_value_audit_v1.json` artifact and packages audited `search_ready` / promoted table values into JSON and JSONL retrieval evidence documents.

The module is intentionally read-only with respect to services. It writes local artifacts only and does not upload to Postgres, Qdrant, or OpenSearch.

Safety contract:

- packaged table evidence is retrieval/search support only
- `can_answer_directly=false`
- `can_prove_claims=false`
- `answer_permission=false`
- `source_truth_mutation_allowed=false`
- `postgres_write_attempt=false`
- `qdrant_write_attempt=false`
- `opensearch_write_attempt=false`

Primary outputs:

- `trace_net_table_route_evidence_packager_v1.json`
- `trace_net_table_route_evidence_documents_v1.jsonl`
- `trace_net_table_route_evidence_packager_v1_quality.json`
- `trace_net_table_route_evidence_packager_v1_inspect.md`

This package prepares the table route for later exact-search/vector-index adapters without giving table extraction final answer authority.
