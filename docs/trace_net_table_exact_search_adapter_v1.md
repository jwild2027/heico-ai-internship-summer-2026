# TRACE-Net Table Exact-Search Adapter v1

Local-only adapter that converts table-route evidence-package records into exact-search documents and OpenSearch-ready local artifacts.

Inputs:

- `local_data/organization/trace_net/table_route_evidence_packager/trace_net_table_route_evidence_packager_v1.json`
- optional sibling JSONL: `trace_net_table_route_evidence_documents_v1.jsonl`

Outputs:

- `trace_net_table_exact_search_adapter_v1.json`
- `trace_net_table_exact_search_documents_v1.jsonl`
- `trace_net_table_exact_search_bulk_v1.ndjson`
- `trace_net_table_exact_search_mapping_v1.json`
- `trace_net_table_exact_search_adapter_v1_inspect.md`

Safety contract:

- retrieval-only documents
- `answer_permission=false`
- `can_answer_directly=false`
- `can_prove_claims=false`
- `source_truth_mutation_allowed=false`
- no Postgres writes
- no Qdrant writes
- no OpenSearch upload/write attempt

This module only prepares local OpenSearch-ready artifacts. It does not contact or upload to OpenSearch.
