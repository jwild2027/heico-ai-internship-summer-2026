# TRACE-Net Graph Query Helper v1

Read-only graph query helper for deterministic source-backed graph lookups.

This module executes bounded, approved graph traversals over the current graph artifacts:

- `part_source_check_v1`: part -> pages -> source links
- `page_source_context_v1`: page -> parts / ATA / source links
- `ata_pages_browse_v1`: ATA section -> pages -> source links

It is not a RAG answerer and it does not grant answer permission. It returns structured source and navigation records for UI, API, retrieval debugging, and future AI trace features.

## Safety contract

- No Postgres writes
- No Qdrant writes
- No OpenSearch writes
- No source-truth mutation
- No answer permission
- No claim-proof authority
- Leiden/community/category hints remain navigation-only

## Build

```bash
python scripts/build_trace_net_graph_query_helper_v1.py \
  --graph-nodes local_data/organization/graph/graph_nodes.json \
  --graph-edges local_data/organization/graph/graph_edges.json \
  --dublin-core-source-package-extension local_data/organization/trace_net/dublin_core_source_package_extension/trace_net_dublin_core_source_package_extension_v1.json \
  --leiden-navigation-metadata-bridge local_data/organization/trace_net/leiden_navigation_metadata_bridge/trace_net_leiden_navigation_metadata_bridge_v1.json \
  --part-number 120-46137-001 \
  --page-id t_p_120_1176_p000003 \
  --ata-code 25-21-00 \
  --output-dir local_data/organization/trace_net/graph_query_helper \
  --max-results-per-query 75 \
  --min-query-records 3 \
  --min-page-results 1 \
  --min-source-resolved-results 1 \
  --min-part-query-results 1 \
  --min-page-query-results 1 \
  --min-ata-query-results 1 \
  --require-graph-nodes \
  --require-graph-edges \
  --require-no-answer-permission \
  --quality
```

## Check

```bash
python scripts/check_trace_net_graph_query_helper_v1_quality.py \
  --report-path local_data/organization/trace_net/graph_query_helper/trace_net_graph_query_helper_v1.json \
  --min-query-records 3 \
  --min-page-results 1 \
  --min-source-resolved-results 1 \
  --min-part-query-results 1 \
  --min-page-query-results 1 \
  --min-ata-query-results 1 \
  --require-graph-nodes \
  --require-graph-edges \
  --require-no-answer-permission \
  --write-json
```
