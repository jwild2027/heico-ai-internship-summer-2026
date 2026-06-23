# TRACE-Net E2E Optional Tunnel Activator v5

Quality status: **PASS**
Status: `E2E_OPTIONAL_TUNNELS_READY_FOR_DYNAMIC_QUERY_TUNNELS_V3`

## Contract
This activator uses prebuilt artifacts only. It does not rerun OCR, page classification, embeddings, summaries, graph construction, table extraction, source ingest, or service writes.

## Summary
- activated_optional_tunnel_count: 4
- graph_or_summary_tunnel_count: 4
- page_summary_tunnel_activated: True
- graph_community_tunnel_activated: True
- graph_navigation_tunnel_activated: True
- table_route_summary_tunnel_activated: True
- answer_permission_count: 0
- can_answer_directly_count: 0
- can_prove_claims_count: 0
- source_truth_mutation_allowed_count: 0
- postgres_write_attempt_count: 0
- qdrant_write_attempt_count: 0
- opensearch_write_attempt_count: 0
- opensearch_upload_attempt_count: 0

## Activated artifacts
- **PASS** `page_summary_tunnel` → `local_data\organization\trace_net\page_context_v2\trace_net_page_context_v2.json` records=509 mode=synthesized_from_page_profiles
- **PASS** `graph_community_tunnel` → `local_data\organization\trace_net\leiden_communities\trace_net_leiden_communities_v1.json` records=229 mode=existing_or_copied
- **PASS** `graph_navigation_tunnel` → `local_data\organization\trace_net\community_navigation_metadata_bridge\trace_net_community_navigation_metadata_bridge_v1.json` records=229 mode=synthesized_from_communities
- **PASS** `table_route_summary_tunnel` → `local_data\organization\trace_net\table_route_retrieval_handoff_summary\trace_net_table_route_retrieval_handoff_summary_v1.json` records=21 mode=existing_or_copied

## Quality checks
- PASS activated_optional_tunnel_count: observed=4 expected=>= 4
- PASS graph_or_summary_tunnel_count: observed=4 expected=>= 2
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS reruns_ocr: observed=0 expected=== 0
- PASS reruns_embeddings: observed=0 expected=== 0
- PASS reruns_graph_build: observed=0 expected=== 0
