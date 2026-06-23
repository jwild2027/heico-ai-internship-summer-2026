# TRACE-Net E2E Dynamic Tunnel Ranker v6

Quality status: **PASS**
Status: `E2E_DYNAMIC_TUNNEL_RANKER_READY_FOR_ENDPOINT_INTEGRATION`

## Contract
This ranker uses prebuilt artifacts only. It does not rerun OCR, page classification, embeddings, summaries, graph construction, table extraction, source ingest, or service writes. Graph and summaries are ranking/navigation hints only, not proof authority.

## Summary
- rank_plan_count: 5
- ready_rank_plan_count: 5
- total_ranked_evidence_count: 25
- unique_contribution_tunnel_count: 8
- plans_with_graph_or_summary_contribution_count: 5
- plans_with_table_contribution_count: 5
- answer_permission_count: 0
- source_truth_mutation_allowed_count: 0

## Available contribution tunnels
- graph_community_tunnel
- graph_navigation_tunnel
- page_summary_tunnel
- qdrant_page_profile_tunnel
- route_metadata_tunnel
- table_exact_search_tunnel
- table_hybrid_bridge_tunnel
- table_route_summary_tunnel

## Rank plans

### Find part number 120-36833-001
- intent: `covered_part_number`
- status: `DYNAMIC_TUNNEL_RANKING_READY`
- contribution tunnels: graph_community_tunnel, graph_navigation_tunnel, page_summary_tunnel, qdrant_page_profile_tunnel, route_metadata_tunnel, table_exact_search_tunnel, table_hybrid_bridge_tunnel, table_route_summary_tunnel
  - rank 1: covered_part_number=120-36833-001 on t_p_120_1176_p000003 score=319
  - rank 2: covered_part_number=120-36833-003 on t_p_120_1176_p000003 score=199
  - rank 3: covered_part_number=120-36833-005 on t_p_120_1176_p000003 score=199

### Find part number 120-36834-509
- intent: `covered_part_number`
- status: `DYNAMIC_TUNNEL_RANKING_READY`
- contribution tunnels: graph_community_tunnel, graph_navigation_tunnel, page_summary_tunnel, qdrant_page_profile_tunnel, route_metadata_tunnel, table_exact_search_tunnel, table_hybrid_bridge_tunnel, table_route_summary_tunnel
  - rank 1: covered_part_number=120-36834-509 on t_p_120_1176_p000003 score=319
  - rank 2: covered_part_number=120-36833-001 on t_p_120_1176_p000003 score=199
  - rank 3: covered_part_number=120-36833-003 on t_p_120_1176_p000003 score=199

### Where is manual reference 25-21-00 used?
- intent: `manual_page_reference`
- status: `DYNAMIC_TUNNEL_RANKING_READY`
- contribution tunnels: graph_community_tunnel, graph_navigation_tunnel, page_summary_tunnel, qdrant_page_profile_tunnel, route_metadata_tunnel, table_exact_search_tunnel, table_hybrid_bridge_tunnel, table_route_summary_tunnel
  - rank 1: manual_page_reference=25-21-00 on t_p_120_1176_p000005 score=319
  - rank 2: ipl_part_number=25-21-00 on t_p_120_1176_p000027 score=299
  - rank 3: ipl_part_number=25-21-00 on t_p_120_1176_p000028 score=299

### Search table text MAINTENANCE MANUAL WITH
- intent: `table_text`
- status: `DYNAMIC_TUNNEL_RANKING_READY`
- contribution tunnels: graph_community_tunnel, graph_navigation_tunnel, page_summary_tunnel, qdrant_page_profile_tunnel, route_metadata_tunnel, table_exact_search_tunnel, table_hybrid_bridge_tunnel, table_route_summary_tunnel
  - rank 1: ipl_text=MAINTENANCE MANUAL WITH on t_p_120_1176_p000027 score=319
  - rank 2: ipl_text=MAINTENANCE MANUAL WITH on t_p_120_1176_p000028 score=319
  - rank 3: ipl_text=MAINTENANCE MANUAL WITH on t_p_120_1176_p000029 score=319

### What maintenance manual pages mention covered part numbers?
- intent: `covered_part_number`
- status: `DYNAMIC_TUNNEL_RANKING_READY`
- contribution tunnels: graph_community_tunnel, graph_navigation_tunnel, page_summary_tunnel, qdrant_page_profile_tunnel, route_metadata_tunnel, table_exact_search_tunnel, table_hybrid_bridge_tunnel, table_route_summary_tunnel
  - rank 1: covered_part_number=120-36833-001 on t_p_120_1176_p000003 score=199
  - rank 2: covered_part_number=120-36833-003 on t_p_120_1176_p000003 score=199
  - rank 3: covered_part_number=120-36833-005 on t_p_120_1176_p000003 score=199

## Quality checks
- PASS rank_plan_count: observed=5 expected=>= 5
- PASS ready_rank_plan_count: observed=5 expected=>= 5
- PASS total_ranked_evidence_count: observed=25 expected=>= 10
- PASS unique_contribution_tunnel_count: observed=8 expected=>= 4
- PASS plans_with_graph_or_summary_contribution_count: observed=5 expected=>= 1
- PASS plans_with_table_contribution_count: observed=5 expected=>= 5
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
