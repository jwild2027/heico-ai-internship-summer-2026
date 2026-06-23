# TRACE-Net E2E Live Orchestrator Stage Timing + Fast Path v27

Quality status: **PASS**
Status: `E2E_LIVE_ORCHESTRATOR_STAGE_TIMING_FASTPATH_READY`

## Summary
- exact_search_document_count: 1497
- page_summary_count: 509
- leiden_page_membership_count: 509
- endpoint_route_count: 4
- sample_query_count: 6
- sample_success_count: 6
- stage_timing_record_count: 6
- fast_path_sample_count: 6
- llm_called_sample_count: 0
- sample_avg_latency_ms: 7.128
- sample_avg_llm_ms: 0.001
- fast_path_mode: exact
- llm_mode: simulate
- llm_model: gemma4:26b
- base_url_windows: http://127.0.0.1:8022/v1
- base_url_open_webui_docker: http://host.docker.internal:8022/v1
- answer_permission_count: 0
- source_truth_mutation_allowed_count: 0

## Contract
- Stage timings are attached to each live response.
- Deterministic fast path may skip the LLM for strict exact lookups and audit-only exact misses.
- LLM output remains draft only; final answers are rebuilt/gated from direct source-truth evidence.
- Graph/Leiden and v2 summaries remain guidance only.
- The endpoint reads prebuilt artifacts and does not scan raw 5TB data or rebuild the graph.

## Sample query results
### Find part number 120-36833-503
- final_gate_status: LIVE_ORCHESTRATOR_FINAL_GATE_PASS
- llm_status: LLM_SKIPPED_FAST_PATH
- fast_path_used: True (exact_lookup_direct_source_truth_answer_ready)
- total_request_ms: 9.514
- llm_draft_ms: 0.001
- final_answer_preview: TRACE-Net found part number 120-36833-503 on page t_p_120_1176_p000003 as covered_part_number [1]. The available direct source-truth evidence confirms the listing, but it does not provide enough information to describe the part physically.

### Find part number DOES-NOT-EXIST-999
- final_gate_status: LIVE_ORCHESTRATOR_AUDIT_ONLY
- llm_status: LLM_SKIPPED_FAST_PATH
- fast_path_used: True (strict_exact_lookup_audit_only_no_evidence)
- total_request_ms: 10.494
- llm_draft_ms: 0.001
- final_answer_preview: TRACE-Net did not find direct citation-ready source-truth evidence for this query. No source-truth claim is made. Try narrowing by part number, manual reference, page, or table text.

### Where is manual reference 25-21-00 used?
- final_gate_status: LIVE_ORCHESTRATOR_FINAL_GATE_PASS
- llm_status: LLM_SKIPPED_FAST_PATH
- fast_path_used: True (exact_lookup_direct_source_truth_answer_ready)
- total_request_ms: 7.186
- llm_draft_ms: 0.001
- final_answer_preview: TRACE-Net found manual reference 25-21-00 on page t_p_120_1176_p000005 [1]. The same page/value was collapsed from 39 repeated source records. Results were capped: TRACE-Net returned 10 of 50 matching records. Available drill-downs include document, manual, revision, section, route, field_type.

### Where is manual reference 99-99-99 used?
- final_gate_status: LIVE_ORCHESTRATOR_AUDIT_ONLY
- llm_status: LLM_SKIPPED_FAST_PATH
- fast_path_used: True (strict_exact_lookup_audit_only_no_evidence)
- total_request_ms: 7.017
- llm_draft_ms: 0.001
- final_answer_preview: TRACE-Net did not find direct citation-ready source-truth evidence for this query. No source-truth claim is made. Try narrowing by part number, manual reference, page, or table text.

### Search table text ILLUSTRATED PARTS LIST
- final_gate_status: LIVE_ORCHESTRATOR_FINAL_GATE_PASS
- llm_status: LLM_SKIPPED_FAST_PATH
- fast_path_used: True (exact_lookup_direct_source_truth_answer_ready)
- total_request_ms: 4.837
- llm_draft_ms: 0.0
- final_answer_preview: TRACE-Net found the exact table text "ILLUSTRATED PARTS LIST" on page t_p_120_1176_p000027 [1]. Nearby OCR/table records were returned as context only and are not treated as direct proof for this query.

### Search table text THIS TEXT DOES NOT EXIST
- final_gate_status: LIVE_ORCHESTRATOR_AUDIT_ONLY
- llm_status: LLM_SKIPPED_FAST_PATH
- fast_path_used: True (strict_exact_lookup_audit_only_no_evidence)
- total_request_ms: 3.723
- llm_draft_ms: 0.0
- final_answer_preview: TRACE-Net did not find direct citation-ready source-truth evidence for this query. No source-truth claim is made. Try narrowing by part number, manual reference, page, or table text.

## Quality checks
- PASS exact_search_document_count: observed=1497 expected=>= 10
- PASS endpoint_route_count: observed=4 expected=>= 4
- PASS sample_query_count: observed=6 expected=>= 6
- PASS sample_success_count: observed=6 expected=>= 6
- PASS stage_timing_record_count: observed=6 expected=>= 6
- PASS fast_path_sample_count: observed=6 expected=>= 5
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS contract_raw_5tb_scan_at_query_time: observed=False expected=is False
- PASS contract_graph_rebuild_at_query_time: observed=False expected=is False
- PASS contract_final_answer_rebuilt_from_source_truth: observed=True expected=is True
- PASS llm_called_sample_count: observed=0 expected=<= 1
- PASS require_no_answer_permission: observed=0 expected=== 0
