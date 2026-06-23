# TRACE-Net E2E Query Planning Routing v1 Inspect

Quality status: **PASS**

## Purpose
This artifact enriches safe query-input records with graph/source-trace and summary tunnels before hybrid retrieval.
The tunnels help route/rank evidence. They do not prove claims or answer directly.

## Routing contract
- retrieval_permission: ranking_only_until_final_gate
- answer_authority: blocked
- graph_and_summaries_are_tunnels: True
- tunnels_can_rank_or_route: True
- tunnels_can_answer_directly: False
- tunnels_can_prove_claims: False
- source_truth_mutation_allowed: False
- writes_to_postgres: False
- writes_to_qdrant: False
- writes_to_opensearch: False
- uploads_to_opensearch: False
- ready_for_hybrid_retrieval_runtime: True

## Main counters
- source_query_input_record_count: 5
- query_route_plan_count: 5
- routeable_query_route_plan_count: 5
- plans_with_graph_tunnel_count: 5
- plans_with_summary_tunnel_count: 5
- plans_with_table_tunnel_count: 5
- total_query_tunnel_count: 30
- unique_tunnel_type_count: 5
- planned_retrieval_step_count: 20
- loaded_summary_artifact_count: 1
- summary_hint_count: 500
- schema_missing_required_key_record_count: 0

## Tunnel type counts
- artifact_graph_summary_tunnel: 15
- graph_source_trace_tunnel: 5
- page_summary_tunnel: 4
- table_route_summary_tunnel: 5
- visual_summary_tunnel: 1

## Safety/write counters
- unsafe_query_route_plan_count: 0
- answer_permission_count: 0
- can_answer_directly_count: 0
- can_prove_claims_count: 0
- source_truth_mutation_allowed_count: 0
- postgres_write_attempt_count: 0
- qdrant_write_attempt_count: 0
- opensearch_write_attempt_count: 0
- opensearch_upload_attempt_count: 0

## Query route plans
- e2e_query_v1_0001 | covered_part_number | query='Find part number 120-36833-001' | tunnels=6
  - graph_source_trace_tunnel | priority=1 | source=route_contract.graph_source_trace
  - page_summary_tunnel | priority=2 | source=summary_profiles.page_context_or_retrieval_profile
  - table_route_summary_tunnel | priority=3 | source=table_route.retrieval_handoff_summary
  - artifact_graph_summary_tunnel | priority=4 | source=local_data\organization\trace_net\page_retrieval_profiles\trace_net_page_retrieval_profiles_v1.json
  - artifact_graph_summary_tunnel | priority=5 | source=local_data\organization\trace_net\page_retrieval_profiles\trace_net_page_retrieval_profiles_v1.json
  - artifact_graph_summary_tunnel | priority=6 | source=local_data\organization\trace_net\page_retrieval_profiles\trace_net_page_retrieval_profiles_v1.json
  - step 1: graph_source_trace_tunnel — anchor source/page/citation neighborhoods
  - step 2: page_summary_tunnel — expand free-text query into page/profile summary neighborhoods
  - step 3: table_exact_and_bridge_tunnel — match table values and apply ranking boosts
  - step 4: final_gate_boundary — do not answer until final TRACE-Net gate reviews the context
- e2e_query_v1_0002 | manual_page_reference | query='Where is manual reference 25-21-00 used?' | tunnels=6
  - graph_source_trace_tunnel | priority=1 | source=route_contract.graph_source_trace
  - page_summary_tunnel | priority=2 | source=summary_profiles.page_context_or_retrieval_profile
  - table_route_summary_tunnel | priority=3 | source=table_route.retrieval_handoff_summary
  - artifact_graph_summary_tunnel | priority=4 | source=local_data\organization\trace_net\page_retrieval_profiles\trace_net_page_retrieval_profiles_v1.json
  - artifact_graph_summary_tunnel | priority=5 | source=local_data\organization\trace_net\page_retrieval_profiles\trace_net_page_retrieval_profiles_v1.json
  - artifact_graph_summary_tunnel | priority=6 | source=local_data\organization\trace_net\page_retrieval_profiles\trace_net_page_retrieval_profiles_v1.json
  - step 1: graph_source_trace_tunnel — anchor source/page/citation neighborhoods
  - step 2: page_summary_tunnel — expand free-text query into page/profile summary neighborhoods
  - step 3: table_exact_and_bridge_tunnel — match table values and apply ranking boosts
  - step 4: final_gate_boundary — do not answer until final TRACE-Net gate reviews the context
- e2e_query_v1_0003 | ipl_figure_item_or_quantity | query='Find IPL item 130' | tunnels=6
  - graph_source_trace_tunnel | priority=1 | source=route_contract.graph_source_trace
  - table_route_summary_tunnel | priority=2 | source=table_route.retrieval_handoff_summary
  - visual_summary_tunnel | priority=3 | source=visual_route.callout_and_figure_summaries
  - artifact_graph_summary_tunnel | priority=4 | source=local_data\organization\trace_net\page_retrieval_profiles\trace_net_page_retrieval_profiles_v1.json
  - artifact_graph_summary_tunnel | priority=5 | source=local_data\organization\trace_net\page_retrieval_profiles\trace_net_page_retrieval_profiles_v1.json
  - artifact_graph_summary_tunnel | priority=6 | source=local_data\organization\trace_net\page_retrieval_profiles\trace_net_page_retrieval_profiles_v1.json
  - step 1: graph_source_trace_tunnel — anchor source/page/citation neighborhoods
  - step 2: table_exact_and_bridge_tunnel — match table values and apply ranking boosts
  - step 3: visual_advisory_tunnel — route IPL/diagram-style query to visual evidence candidates
  - step 4: final_gate_boundary — do not answer until final TRACE-Net gate reviews the context
- e2e_query_v1_0004 | table_text | query='Search table text MAINTENANCE MANUAL WITH' | tunnels=6
  - graph_source_trace_tunnel | priority=1 | source=route_contract.graph_source_trace
  - page_summary_tunnel | priority=2 | source=summary_profiles.page_context_or_retrieval_profile
  - table_route_summary_tunnel | priority=3 | source=table_route.retrieval_handoff_summary
  - artifact_graph_summary_tunnel | priority=4 | source=local_data\organization\trace_net\page_retrieval_profiles\trace_net_page_retrieval_profiles_v1.json
  - artifact_graph_summary_tunnel | priority=5 | source=local_data\organization\trace_net\page_retrieval_profiles\trace_net_page_retrieval_profiles_v1.json
  - artifact_graph_summary_tunnel | priority=6 | source=local_data\organization\trace_net\page_retrieval_profiles\trace_net_page_retrieval_profiles_v1.json
  - step 1: graph_source_trace_tunnel — anchor source/page/citation neighborhoods
  - step 2: page_summary_tunnel — expand free-text query into page/profile summary neighborhoods
  - step 3: table_exact_and_bridge_tunnel — match table values and apply ranking boosts
  - step 4: final_gate_boundary — do not answer until final TRACE-Net gate reviews the context
- e2e_query_v1_0005 | covered_part_number | query='What maintenance manual pages mention covered part numbers?' | tunnels=6
  - graph_source_trace_tunnel | priority=1 | source=route_contract.graph_source_trace
  - page_summary_tunnel | priority=2 | source=summary_profiles.page_context_or_retrieval_profile
  - table_route_summary_tunnel | priority=3 | source=table_route.retrieval_handoff_summary
  - artifact_graph_summary_tunnel | priority=4 | source=local_data\organization\trace_net\page_retrieval_profiles\trace_net_page_retrieval_profiles_v1.json
  - artifact_graph_summary_tunnel | priority=5 | source=local_data\organization\trace_net\page_retrieval_profiles\trace_net_page_retrieval_profiles_v1.json
  - artifact_graph_summary_tunnel | priority=6 | source=local_data\organization\trace_net\page_retrieval_profiles\trace_net_page_retrieval_profiles_v1.json
  - step 1: graph_source_trace_tunnel — anchor source/page/citation neighborhoods
  - step 2: page_summary_tunnel — expand free-text query into page/profile summary neighborhoods
  - step 3: table_exact_and_bridge_tunnel — match table values and apply ranking boosts
  - step 4: final_gate_boundary — do not answer until final TRACE-Net gate reviews the context

## Quality checks
- PASS source_query_input_record_count: observed=5 expected=>= 5
- PASS query_route_plan_count: observed=5 expected=>= 5
- PASS routeable_query_route_plan_count: observed=5 expected=>= 5
- PASS plans_with_graph_tunnel_count: observed=5 expected=>= 5
- PASS plans_with_summary_tunnel_count: observed=5 expected=>= 5
- PASS plans_with_table_tunnel_count: observed=5 expected=>= 5
- PASS total_query_tunnel_count: observed=30 expected=>= 15
- PASS unique_tunnel_type_count: observed=5 expected=>= 3
- PASS planned_retrieval_step_count: observed=20 expected=>= 15
- PASS schema_missing_required_key_record_count: observed=0 expected=<= 0
- PASS unsafe_query_route_plan_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS can_answer_directly_count: observed=0 expected=== 0
- PASS can_prove_claims_count: observed=0 expected=== 0
- PASS postgres_write_attempt_count: observed=0 expected=== 0
- PASS qdrant_write_attempt_count: observed=0 expected=== 0
- PASS opensearch_write_attempt_count: observed=0 expected=== 0
- PASS opensearch_upload_attempt_count: observed=0 expected=== 0
- PASS source_query_input_quality_pass: observed=True expected=is True
- PASS all_plans_retrieval_only: observed=True expected=is True
