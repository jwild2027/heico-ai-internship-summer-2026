# TRACE-Net E2E LLM-Assisted Query Planner v17

Quality status: **PASS**
Status: `E2E_LLM_ASSISTED_QUERY_PLANNER_READY_FOR_DYNAMIC_PLAN_EXECUTION`

## Summary
- query_plan_count: 5
- validated_query_plan_count: 5
- plans_with_v2_summary_guidance_count: 5
- plans_with_leiden_guidance_count: 5
- plans_with_source_truth_fields_count: 5
- allowed_tunnel_validation_count: 40
- invalid_tunnel_count: 0
- proof_authority_violation_count: 0
- answer_permission_count: 0
- source_truth_mutation_allowed_count: 0

## Contract
- LLM may propose structured query plans, but TRACE-Net validates every plan before execution.
- TRACE-Net executes only allowed tunnels.
- v2 summaries are guidance only, not proof authority.
- Leiden communities are graph/navigation guidance only, not proof authority.
- Source-truth evidence is required for final claims.
- Query-time planning must not scan raw 5TB source data; it uses prebuilt indexes, summaries, graph metadata, and evidence artifacts.

## Query plans
### query_plan_v17_0001 — `part_number`
- query: Find part number 120-36834-509
- status: `QUERY_PLAN_VALIDATED_FOR_TUNNEL_EXECUTION`
- primary_tunnels: table_exact_search_tunnel
- guidance_tunnels: page_summary_tunnel, graph_community_tunnel, graph_navigation_tunnel, route_metadata_tunnel, table_route_summary_tunnel
- required_source_truth_fields: covered_part_number, ipl_part_number, part_number

### query_plan_v17_0002 — `part_number`
- query: Find part number 120-36833-501
- status: `QUERY_PLAN_VALIDATED_FOR_TUNNEL_EXECUTION`
- primary_tunnels: table_exact_search_tunnel
- guidance_tunnels: page_summary_tunnel, graph_community_tunnel, graph_navigation_tunnel, route_metadata_tunnel, table_route_summary_tunnel
- required_source_truth_fields: covered_part_number, ipl_part_number, part_number

### query_plan_v17_0003 — `covered_part_number`
- query: What maintenance manual pages mention covered part numbers?
- status: `QUERY_PLAN_VALIDATED_FOR_TUNNEL_EXECUTION`
- primary_tunnels: table_exact_search_tunnel
- guidance_tunnels: page_summary_tunnel, graph_community_tunnel, graph_navigation_tunnel, route_metadata_tunnel, table_route_summary_tunnel
- required_source_truth_fields: covered_part_number

### query_plan_v17_0004 — `manual_page_reference`
- query: Where is manual reference 25-21-00 used?
- status: `QUERY_PLAN_VALIDATED_FOR_TUNNEL_EXECUTION`
- primary_tunnels: table_exact_search_tunnel
- guidance_tunnels: page_summary_tunnel, graph_community_tunnel, graph_navigation_tunnel, route_metadata_tunnel, table_route_summary_tunnel
- required_source_truth_fields: manual_page_reference, ipl_part_number

### query_plan_v17_0005 — `table_text`
- query: Search table text MAINTENANCE MANUAL WITH
- status: `QUERY_PLAN_VALIDATED_FOR_TUNNEL_EXECUTION`
- primary_tunnels: table_exact_search_tunnel
- guidance_tunnels: page_summary_tunnel, graph_community_tunnel, graph_navigation_tunnel, route_metadata_tunnel, table_route_summary_tunnel
- required_source_truth_fields: ipl_text, table_text

## Quality checks
- PASS query_plan_count: observed=5 expected=>= 5
- PASS validated_query_plan_count: observed=5 expected=>= 5
- PASS plans_with_v2_summary_guidance_count: observed=5 expected=>= 5
- PASS plans_with_leiden_guidance_count: observed=5 expected=>= 5
- PASS plans_with_source_truth_fields_count: observed=5 expected=>= 5
- PASS allowed_tunnel_validation_count: observed=40 expected=>= 20
- PASS invalid_tunnel_count: observed=0 expected=<= 0
- PASS proof_authority_violation_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS require_no_answer_permission: observed=0 expected=== 0
