# TRACE-Net Graph Query Evidence Enrichment v1

Read-only enrichment layer for controlled graph query results.

This module keeps Graph Query Helper v1 as the deterministic organization-graph lookup layer, then adds TRACE-Net v2 evidence context from OpenSearch, Hybrid Retrieval, Leiden navigation metadata, Dublin Core source identity, and claim-evidence entailment diagnostics.

## Safety contract

- No Postgres writes
- No Qdrant writes
- No OpenSearch writes
- No source-truth mutation
- No answer permission
- No claim-proof authority

All enriched records remain retrieval-only and must still pass the final answer gate before any user-facing answer can be returned.

## Main inputs

- `local_data/organization/trace_net/graph_query_helper/trace_net_graph_query_helper_v1.json`
- `local_data/organization/trace_net/opensearch_adapter/trace_net_opensearch_adapter_v1.json`
- `local_data/organization/trace_net/hybrid_retrieval_v2/trace_net_hybrid_retrieval_v2.json`
- `local_data/organization/trace_net/leiden_navigation_metadata_bridge/trace_net_leiden_navigation_metadata_bridge_v1.json`
- `local_data/organization/trace_net/dublin_core_source_package_extension/trace_net_dublin_core_source_package_extension_v1.json`
- `local_data/organization/trace_net/claim_evidence_entailment/trace_net_claim_evidence_entailment_v1.json`

## Main outputs

- `trace_net_graph_query_evidence_enrichment_v1.json`
- `trace_net_graph_query_evidence_enrichment_v1_quality.json`
- `trace_net_graph_query_evidence_enrichment_v1_records.jsonl`
- `trace_net_graph_query_evidence_enrichment_v1_page_evidence.jsonl`

## Intent

Graph Query API v1 currently exposes controlled organization-graph paths such as part to page to source. This module enriches those graph results with evidence context so a part query can show:

- organization graph pages
- exact OpenSearch evidence pages
- Hybrid Retrieval pages
- Leiden navigation pages
- claim-entailment review/alignment warnings

It does not replace the final answer gate.
