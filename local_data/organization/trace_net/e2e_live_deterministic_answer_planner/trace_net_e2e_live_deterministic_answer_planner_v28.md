# TRACE-Net E2E Live Deterministic Answer Planner + Drilldown v28

Quality status: **PASS**
Status: `E2E_LIVE_DETERMINISTIC_ANSWER_PLANNER_READY`

## Summary
- exact_search_document_count: 1497
- page_summary_count: 509
- leiden_page_membership_count: 509
- endpoint_route_count: 4
- sample_query_count: 8
- sample_success_count: 8
- stage_timing_record_count: 8
- deterministic_answer_sample_count: 8
- drilldown_sample_count: 1
- llm_called_sample_count: 0
- sample_avg_latency_ms: 4.921
- sample_avg_llm_ms: 0.001
- deterministic_mode: expanded
- response_mode_counts: {'exact_single_value': 3, 'exact_missing_value': 3, 'capped_listing': 1, 'drilldown_request': 1}
- llm_mode: simulate
- llm_model: gemma4:26b
- base_url_windows: http://127.0.0.1:8023/v1
- base_url_open_webui_docker: http://host.docker.internal:8023/v1
- answer_permission_count: 0
- source_truth_mutation_allowed_count: 0

## Contract
- Expanded deterministic answer planner may skip the LLM for exact values, field listings, capped listings, and drill-down requests.
- Relationship/synthesis questions remain eligible for the LLM.
- Final answers are rebuilt/gated from direct source-truth evidence.
- Graph/Leiden, v2 summaries, nearby OCR, and aggregation metadata remain guidance/disclosure only.
- The endpoint reads prebuilt artifacts and does not scan raw 5TB data or rebuild the graph.

## Sample query results
### Find part number 120-36833-503
- response_mode: exact_single_value
- final_gate_status: LIVE_ORCHESTRATOR_FINAL_GATE_PASS
- llm_status: LLM_SKIPPED_DETERMINISTIC_PLANNER
- deterministic_answer_planner_used: True
- deterministic_answer_reason: deterministic_exact_single_value_source_truth_ready
- total_request_ms: 8.863
- llm_draft_ms: 0.0
- raw_candidate_match_count: 1
- target_unique_match_count: 1
- target_occurrence_count: 1
- collapsed_duplicate_record_count: 0
- final_answer_preview: TRACE-Net found part number 120-36833-503 on page t_p_120_1176_p000003 as covered_part_number [1]. The available direct source-truth evidence confirms the listing, but it does not provide enough information to describe the part physically.

### Find part number DOES-NOT-EXIST-999
- response_mode: exact_missing_value
- final_gate_status: LIVE_ORCHESTRATOR_AUDIT_ONLY
- llm_status: LLM_SKIPPED_DETERMINISTIC_PLANNER
- deterministic_answer_planner_used: True
- deterministic_answer_reason: deterministic_exact_missing_value_source_truth_ready
- total_request_ms: 6.06
- llm_draft_ms: 0.0
- raw_candidate_match_count: 0
- target_unique_match_count: 0
- target_occurrence_count: 0
- collapsed_duplicate_record_count: 0
- final_answer_preview: TRACE-Net did not find direct citation-ready source-truth evidence for this query. No source-truth claim is made. Try narrowing by part number, manual reference, page, or table text.

### Where is manual reference 25-21-00 used?
- response_mode: exact_single_value
- final_gate_status: LIVE_ORCHESTRATOR_FINAL_GATE_PASS
- llm_status: LLM_SKIPPED_DETERMINISTIC_PLANNER
- deterministic_answer_planner_used: True
- deterministic_answer_reason: deterministic_exact_single_value_source_truth_ready
- total_request_ms: 4.324
- llm_draft_ms: 0.001
- raw_candidate_match_count: 50
- target_unique_match_count: 10
- target_occurrence_count: 48
- collapsed_duplicate_record_count: 38
- final_answer_preview: TRACE-Net found manual reference 25-21-00 on page t_p_120_1176_p000005 [1]. The same page/value was collapsed from 38 repeated source records. Strict target filtering was applied; raw candidate matches before filtering: 50.

### Where is manual reference 99-99-99 used?
- response_mode: exact_missing_value
- final_gate_status: LIVE_ORCHESTRATOR_AUDIT_ONLY
- llm_status: LLM_SKIPPED_DETERMINISTIC_PLANNER
- deterministic_answer_planner_used: True
- deterministic_answer_reason: deterministic_exact_missing_value_source_truth_ready
- total_request_ms: 6.097
- llm_draft_ms: 0.001
- raw_candidate_match_count: 0
- target_unique_match_count: 0
- target_occurrence_count: 0
- collapsed_duplicate_record_count: 0
- final_answer_preview: TRACE-Net did not find direct citation-ready source-truth evidence for this query. No source-truth claim is made. Try narrowing by part number, manual reference, page, or table text.

### Search table text ILLUSTRATED PARTS LIST
- response_mode: exact_single_value
- final_gate_status: LIVE_ORCHESTRATOR_FINAL_GATE_PASS
- llm_status: LLM_SKIPPED_DETERMINISTIC_PLANNER
- deterministic_answer_planner_used: True
- deterministic_answer_reason: deterministic_exact_single_value_source_truth_ready
- total_request_ms: 6.574
- llm_draft_ms: 0.001
- raw_candidate_match_count: 10
- target_unique_match_count: 10
- target_occurrence_count: 10
- collapsed_duplicate_record_count: 0
- final_answer_preview: TRACE-Net found the exact table text "ILLUSTRATED PARTS LIST" on page t_p_120_1176_p000027 [1]. Nearby OCR/table records were returned as context only and are not treated as direct proof for this query.

### Search table text THIS TEXT DOES NOT EXIST
- response_mode: exact_missing_value
- final_gate_status: LIVE_ORCHESTRATOR_AUDIT_ONLY
- llm_status: LLM_SKIPPED_DETERMINISTIC_PLANNER
- deterministic_answer_planner_used: True
- deterministic_answer_reason: deterministic_exact_missing_value_source_truth_ready
- total_request_ms: 4.576
- llm_draft_ms: 0.001
- raw_candidate_match_count: 0
- target_unique_match_count: 0
- target_occurrence_count: 0
- collapsed_duplicate_record_count: 0
- final_answer_preview: TRACE-Net did not find direct citation-ready source-truth evidence for this query. No source-truth claim is made. Try narrowing by part number, manual reference, page, or table text.

### What maintenance manual pages mention covered part numbers?
- response_mode: capped_listing
- final_gate_status: LIVE_ORCHESTRATOR_FINAL_GATE_PASS
- llm_status: LLM_SKIPPED_DETERMINISTIC_PLANNER
- deterministic_answer_planner_used: True
- deterministic_answer_reason: deterministic_capped_listing_source_truth_ready
- total_request_ms: 1.557
- llm_draft_ms: 0.001
- raw_candidate_match_count: 150
- target_unique_match_count: 10
- target_occurrence_count: 10
- collapsed_duplicate_record_count: 0
- final_answer_preview: TRACE-Net found covered part numbers on page(s) t_p_120_1176_p000003. Direct source-truth examples include 120-36833-001 [1]; 120-36833-003 [2]; 120-36833-005 [3]; 120-36833-501 [4]; 120-36833-503 [5]; 120-36833-507 [6]; 120-36833-509 [7]; 120-36833-511 [8]; 120-36833-513 [9]; 120-36833-515 [10]. Results were capped: TRACE-Net returned 10 of 150 matching records. Available drill-downs include document, manual, revision, section, route, field_type.

### Drill down covered part numbers by page
- response_mode: drilldown_request
- final_gate_status: LIVE_ORCHESTRATOR_FINAL_GATE_PASS
- llm_status: LLM_SKIPPED_DETERMINISTIC_PLANNER
- deterministic_answer_planner_used: True
- deterministic_answer_reason: deterministic_drilldown_request_source_truth_ready
- total_request_ms: 1.314
- llm_draft_ms: 0.001
- raw_candidate_match_count: 150
- target_unique_match_count: 10
- target_occurrence_count: 10
- collapsed_duplicate_record_count: 0
- final_answer_preview: TRACE-Net drill-down by page: t_p_120_1176_p000003: 150. Direct source-truth examples include 120-36833-001 [1]; 120-36833-003 [2]; 120-36833-005 [3]; 120-36833-501 [4]; 120-36833-503 [5]; 120-36833-507 [6]; 120-36833-509 [7]; 120-36833-511 [8]; 120-36833-513 [9]; 120-36833-515 [10]. Results were capped: TRACE-Net returned 10 of 150 matching records. Available drill-downs include document, manual, revision, section, route, field_type.

## Quality checks
- PASS exact_search_document_count: observed=1497 expected=>= 10
- PASS endpoint_route_count: observed=4 expected=>= 4
- PASS sample_query_count: observed=8 expected=>= 8
- PASS sample_success_count: observed=8 expected=>= 8
- PASS stage_timing_record_count: observed=8 expected=>= 8
- PASS deterministic_answer_sample_count: observed=8 expected=>= 8
- PASS drilldown_sample_count: observed=1 expected=>= 1
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS contract_raw_5tb_scan_at_query_time: observed=False expected=is False
- PASS contract_graph_rebuild_at_query_time: observed=False expected=is False
- PASS contract_final_answer_rebuilt_from_source_truth: observed=True expected=is True
- PASS contract_drilldown_supported: observed=True expected=is True
- PASS llm_called_sample_count: observed=0 expected=<= 0
- PASS require_no_answer_permission: observed=0 expected=== 0

report_path: `local_data\organization\trace_net\e2e_live_deterministic_answer_planner\trace_net_e2e_live_deterministic_answer_planner_v28.json`
sample_jsonl_path: `local_data\organization\trace_net\e2e_live_deterministic_answer_planner\trace_net_e2e_live_deterministic_answer_planner_samples_v28.jsonl`
