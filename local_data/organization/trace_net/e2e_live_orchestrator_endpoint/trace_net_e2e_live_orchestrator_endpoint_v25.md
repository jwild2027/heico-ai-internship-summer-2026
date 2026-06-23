# TRACE-Net E2E Live Orchestrator Endpoint v25

Quality status: **PASS**
Status: `E2E_LIVE_ORCHESTRATOR_ENDPOINT_READY`

## Summary
- exact_search_document_count: 1497
- page_summary_count: 509
- leiden_page_membership_count: 509
- endpoint_route_count: 4
- sample_query_count: 5
- sample_success_count: 5
- llm_mode: simulate
- llm_model: gemma4:26b
- base_url_windows: http://127.0.0.1:8021/v1
- base_url_open_webui_docker: http://host.docker.internal:8021/v1
- answer_permission_count: 0
- source_truth_mutation_allowed_count: 0

## Contract
- This endpoint runs a compact live query pipeline at request time.
- The LLM output is a draft only; final answers are rebuilt/gated from direct source-truth evidence.
- Graph/Leiden and v2 summaries remain guidance only.
- Nearby context is not direct proof.
- The endpoint reads prebuilt indexes/artifacts and does not scan raw 5TB data or rebuild the graph.

## Sample query results
### Find part number 120-36834-509
- final_gate_status: LIVE_ORCHESTRATOR_FINAL_GATE_PASS
- llm_status: LLM_SIMULATED
- final_answer_preview: TRACE-Net found part number 120-36834-509 on page t_p_120_1176_p000003 as covered_part_number [1]. The available direct source-truth evidence confirms the listing, but it does not provide enough information to describe the part physically.

### Find part number 120-36833-501
- final_gate_status: LIVE_ORCHESTRATOR_FINAL_GATE_PASS
- llm_status: LLM_SIMULATED
- final_answer_preview: TRACE-Net found part number 120-36833-501 on page t_p_120_1176_p000003 as covered_part_number [1]. The available direct source-truth evidence confirms the listing, but it does not provide enough information to describe the part physically.

### What maintenance manual pages mention covered part numbers?
- final_gate_status: LIVE_ORCHESTRATOR_FINAL_GATE_PASS
- llm_status: LLM_SIMULATED
- final_answer_preview: TRACE-Net found covered part numbers on page(s) t_p_120_1176_p000003. Direct source-truth examples include 120-36833-001 [1]; 120-36833-003 [2]; 120-36833-005 [3]; 120-36833-501 [4]; 120-36833-503 [5]; 120-36833-507 [6]; 120-36833-509 [7]; 120-36833-511 [8]; 120-36833-513 [9]; 120-36833-515 [10]. Results were capped: TRACE-Net returned 10 of 150 matching records. Available drill-downs include document, manual, revision, section, route, field_type.

### Where is manual reference 25-21-00 used?
- final_gate_status: LIVE_ORCHESTRATOR_FINAL_GATE_PASS
- llm_status: LLM_SIMULATED
- final_answer_preview: TRACE-Net found manual reference 25-21-00 on page t_p_120_1176_p000005 [1]. The same page/value was collapsed from 39 repeated source records. Results were capped: TRACE-Net returned 10 of 50 matching records. Available drill-downs include document, manual, revision, section, route, field_type.

### Search table text MAINTENANCE MANUAL WITH
- final_gate_status: LIVE_ORCHESTRATOR_FINAL_GATE_PASS
- llm_status: LLM_SIMULATED
- final_answer_preview: TRACE-Net found the exact table text "MAINTENANCE MANUAL WITH" on page t_p_120_1176_p000027 [1]. Nearby OCR/table records were returned as context only and are not treated as direct proof for this query.

## Quality checks
- PASS exact_search_document_count: observed=1497 expected=>= 10
- PASS endpoint_route_count: observed=4 expected=>= 4
- PASS sample_query_count: observed=5 expected=>= 5
- PASS sample_success_count: observed=5 expected=>= 5
- PASS sample_unsupported_claim_count: observed=0 expected=<= 0
- PASS sample_llm_call_error_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS contract_raw_5tb_scan_at_query_time: observed=False expected=is False
- PASS contract_graph_rebuild_at_query_time: observed=False expected=is False
- PASS require_no_answer_permission: observed=0 expected=== 0
