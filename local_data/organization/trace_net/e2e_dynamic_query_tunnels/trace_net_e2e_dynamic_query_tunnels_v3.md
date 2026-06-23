# TRACE-Net E2E Dynamic Query Tunnels v3

Quality status: **PASS**
Status: `E2E_DYNAMIC_QUERY_TUNNELS_READY_FOR_ENDPOINT_INTEGRATION`

## Hybrid tunnel assessment
Dynamic v3 adds query-time tunnel plans over prebuilt table exact-search, table bridge, page/profile summaries, graph/community navigation, and route metadata when those artifacts are present. It does not rebuild corpus artifacts and does not grant answer authority.

## Summary
- query_tunnel_plan_count: 5
- ready_query_tunnel_plan_count: 5
- total_tunnel_count: 40
- unique_tunnel_type_count: 8
- available_artifact_count: 9
- plans_with_table_tunnel_count: 5
- plans_with_qdrant_page_profile_tunnel_count: 5
- plans_with_graph_tunnel_count: 10
- plans_with_summary_tunnel_count: 10
- plans_with_route_metadata_tunnel_count: 5
- answer_permission_count: 0
- can_answer_directly_count: 0
- can_prove_claims_count: 0
- source_truth_mutation_allowed_count: 0

## Available artifacts
- **PASS** `dynamic_query_endpoint_manifest` → `dynamic_endpoint_contract` quality=PASS records=0
- **PASS** `table_exact_search_adapter` → `table_exact_search_tunnel` quality=PASS records=1497
- **PASS** `table_hybrid_retrieval_bridge` → `table_hybrid_bridge_tunnel` quality=PASS records=1497
- **PASS** `page_retrieval_profiles` → `qdrant_page_profile_tunnel` quality=UNKNOWN records=509
- **PASS** `page_context_v2` → `page_summary_tunnel` quality=PASS records=0
- **PASS** `leiden_communities` → `graph_community_tunnel` quality=PASS records=229
- **PASS** `community_navigation_metadata_bridge` → `graph_navigation_tunnel` quality=PASS records=229
- **PASS** `route_dispatch_manifest` → `route_metadata_tunnel` quality=PASS records=0
- **PASS** `table_route_retrieval_handoff_summary` → `table_route_summary_tunnel` quality=PASS records=1497

## Query tunnel plans

### Find part number 120-36833-001
- intent: `covered_part_number`
- status: `DYNAMIC_TUNNEL_PLAN_READY`
- tunnels: table_exact_search_tunnel, table_hybrid_bridge_tunnel, route_metadata_tunnel, table_route_summary_tunnel, qdrant_page_profile_tunnel, graph_navigation_tunnel, page_summary_tunnel, graph_community_tunnel

### Find part number 120-36834-509
- intent: `covered_part_number`
- status: `DYNAMIC_TUNNEL_PLAN_READY`
- tunnels: table_exact_search_tunnel, table_hybrid_bridge_tunnel, route_metadata_tunnel, table_route_summary_tunnel, qdrant_page_profile_tunnel, graph_navigation_tunnel, page_summary_tunnel, graph_community_tunnel

### Where is manual reference 25-21-00 used?
- intent: `manual_page_reference`
- status: `DYNAMIC_TUNNEL_PLAN_READY`
- tunnels: table_exact_search_tunnel, table_hybrid_bridge_tunnel, route_metadata_tunnel, graph_navigation_tunnel, page_summary_tunnel, qdrant_page_profile_tunnel, graph_community_tunnel, table_route_summary_tunnel

### Search table text MAINTENANCE MANUAL WITH
- intent: `table_text`
- status: `DYNAMIC_TUNNEL_PLAN_READY`
- tunnels: table_exact_search_tunnel, table_hybrid_bridge_tunnel, page_summary_tunnel, route_metadata_tunnel, qdrant_page_profile_tunnel, graph_navigation_tunnel, graph_community_tunnel, table_route_summary_tunnel

### What maintenance manual pages mention covered part numbers?
- intent: `covered_part_number`
- status: `DYNAMIC_TUNNEL_PLAN_READY`
- tunnels: table_exact_search_tunnel, table_hybrid_bridge_tunnel, route_metadata_tunnel, table_route_summary_tunnel, qdrant_page_profile_tunnel, graph_navigation_tunnel, page_summary_tunnel, graph_community_tunnel
