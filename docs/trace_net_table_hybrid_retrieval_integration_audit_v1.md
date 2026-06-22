# TRACE-Net Table Hybrid Retrieval Integration Audit v1

Local-only audit proving table hybrid-retrieval bridge records are available to retrieval ranking while remaining blocked from final-answer authority.

Input:

- `table_hybrid_retrieval_bridge/trace_net_table_hybrid_retrieval_bridge_v1.json`

Outputs:

- `trace_net_table_hybrid_retrieval_integration_audit_v1.json`
- `trace_net_table_hybrid_retrieval_integration_audit_records_v1.jsonl`
- `trace_net_table_hybrid_retrieval_integration_audit_v1_inspect.md`

Safety contract:

- table bridge records are ranking signals only
- no answer permission
- no claim proof
- no source-truth mutation
- no Postgres, Qdrant, OpenSearch, or upload writes
