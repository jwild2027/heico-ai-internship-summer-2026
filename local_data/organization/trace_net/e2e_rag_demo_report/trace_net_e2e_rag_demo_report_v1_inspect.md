# TRACE-Net E2E RAG Demo Report v1 Inspect

Quality status: **PASS**

## Demo status
- e2e_rag_demo_status: E2E_RAG_DEMO_REPORT_READY_FOR_API_WRAPPER
- graph and summaries are tunnels: True
- answer authority: blocked in artifact smoke
- ready for API wrapper: True

## Main counters
- stage_pass_count: 5
- e2e_demo_record_count: 5
- complete_demo_flow_count: 5
- planned_query_route_plan_count: 5
- total_query_tunnel_count: 30
- retrieval_group_count: 5
- successful_retrieval_query_count: 5
- total_retrieval_hit_count: 50
- context_pack_count: 5
- total_context_item_count: 25
- final_gate_review_ready_pack_count: 5
- final_gate_record_count: 5
- safe_response_draft_count: 5
- citation_backed_response_draft_count: 5
- total_citation_count: 15
- page_with_citation_count: 6
- field_count: 5

## Safety/write counters
- unsafe_total_count: 0
- answer_permission_count: 0
- can_answer_directly_count: 0
- can_prove_claims_count: 0
- source_truth_mutation_allowed_count: 0
- postgres_write_attempt_count: 0
- qdrant_write_attempt_count: 0
- opensearch_write_attempt_count: 0
- opensearch_upload_attempt_count: 0

## Demo records
- e2e_query_v1_0001 | covered_part_number | E2E_DEMO_FLOW_COMPLETE | retrieval_hits=10 | citations=3
  - query: Find part number 120-36833-001
  - final_gate_decision: FINAL_GATE_SAFE_CITATION_BACKED_RESPONSE_DRAFT
  - pages: t_p_120_1176_p000003
  - draft: Final-gate smoke draft for query: 'Find part number 120-36833-001'. TRACE-Net found citation/source-trace-ready evidence: covered_part_number=120-36833-001 on t_p_120_1176_p000003; covered_part_number=120-36833-003 on t_p_120_1176_p000003; 
- e2e_query_v1_0002 | manual_page_reference | E2E_DEMO_FLOW_COMPLETE | retrieval_hits=10 | citations=3
  - query: Where is manual reference 25-21-00 used?
  - final_gate_decision: FINAL_GATE_SAFE_CITATION_BACKED_RESPONSE_DRAFT
  - pages: t_p_120_1176_p000005, t_p_120_1176_p000027, t_p_120_1176_p000028, t_p_120_1176_p000029, t_p_120_1176_p000030, t_p_120_1176_p000031, t_p_120_1176_p000032, t_p_120_1176_p000033
  - draft: Final-gate smoke draft for query: 'Where is manual reference 25-21-00 used?'. TRACE-Net found citation/source-trace-ready evidence: manual_page_reference=25-21-00 on t_p_120_1176_p000005; ipl_part_number=25-21-00 on t_p_120_1176_p000027; ip
- e2e_query_v1_0003 | ipl_figure_item_or_quantity | E2E_DEMO_FLOW_COMPLETE | retrieval_hits=10 | citations=3
  - query: Find IPL item 130
  - final_gate_decision: FINAL_GATE_SAFE_CITATION_BACKED_RESPONSE_DRAFT
  - pages: t_p_120_1176_p000027, t_p_120_1176_p000028, t_p_120_1176_p000036
  - draft: Final-gate smoke draft for query: 'Find IPL item 130'. TRACE-Net found citation/source-trace-ready evidence: ipl_figure_item_or_quantity=130 on t_p_120_1176_p000027; ipl_figure_item_or_quantity=130 on t_p_120_1176_p000028; ipl_figure_item_o
- e2e_query_v1_0004 | table_text | E2E_DEMO_FLOW_COMPLETE | retrieval_hits=10 | citations=3
  - query: Search table text MAINTENANCE MANUAL WITH
  - final_gate_decision: FINAL_GATE_SAFE_CITATION_BACKED_RESPONSE_DRAFT
  - pages: t_p_120_1176_p000027, t_p_120_1176_p000028, t_p_120_1176_p000029, t_p_120_1176_p000030, t_p_120_1176_p000031, t_p_120_1176_p000032, t_p_120_1176_p000033, t_p_120_1176_p000034
  - draft: Final-gate smoke draft for query: 'Search table text MAINTENANCE MANUAL WITH'. TRACE-Net found citation/source-trace-ready evidence: ipl_text=MAINTENANCE MANUAL WITH on t_p_120_1176_p000027; ipl_text=MAINTENANCE MANUAL WITH on t_p_120_1176_
- e2e_query_v1_0005 | covered_part_number | E2E_DEMO_FLOW_COMPLETE | retrieval_hits=10 | citations=3
  - query: What maintenance manual pages mention covered part numbers?
  - final_gate_decision: FINAL_GATE_SAFE_CITATION_BACKED_RESPONSE_DRAFT
  - pages: t_p_120_1176_p000003
  - draft: Final-gate smoke draft for query: 'What maintenance manual pages mention covered part numbers?'. TRACE-Net found citation/source-trace-ready evidence: covered_part_number=120-36833-001 on t_p_120_1176_p000003; covered_part_number=120-36833-

## Quality checks
- PASS source_planning_quality_pass: observed=True expected=is True
- PASS source_runtime_quality_pass: observed=True expected=is True
- PASS source_context_quality_pass: observed=True expected=is True
- PASS source_sufficiency_quality_pass: observed=True expected=is True
- PASS source_final_gate_smoke_quality_pass: observed=True expected=is True
- PASS stage_pass_count: observed=5 expected=>= 5
- PASS e2e_demo_record_count: observed=5 expected=>= 5
- PASS complete_demo_flow_count: observed=5 expected=>= 5
- PASS planned_query_route_plan_count: observed=5 expected=>= 5
- PASS total_query_tunnel_count: observed=30 expected=>= 15
- PASS retrieval_group_count: observed=5 expected=>= 5
- PASS successful_retrieval_query_count: observed=5 expected=>= 4
- PASS context_pack_count: observed=5 expected=>= 5
- PASS final_gate_review_ready_pack_count: observed=5 expected=>= 4
- PASS final_gate_record_count: observed=5 expected=>= 5
- PASS safe_response_draft_count: observed=5 expected=>= 4
- PASS citation_backed_response_draft_count: observed=5 expected=>= 4
- PASS total_citation_count: observed=15 expected=>= 10
- PASS page_with_citation_count: observed=6 expected=>= 2
- PASS field_count: observed=5 expected=>= 3
- PASS schema_missing_required_key_record_count: observed=0 expected=<= 0
- PASS unsafe_total_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS can_answer_directly_count: observed=0 expected=== 0
- PASS can_prove_claims_count: observed=0 expected=== 0
- PASS postgres_write_attempt_count: observed=0 expected=== 0
- PASS qdrant_write_attempt_count: observed=0 expected=== 0
- PASS opensearch_write_attempt_count: observed=0 expected=== 0
- PASS opensearch_upload_attempt_count: observed=0 expected=== 0
- PASS all_demo_records_no_answer_authority: observed=True expected=is True
