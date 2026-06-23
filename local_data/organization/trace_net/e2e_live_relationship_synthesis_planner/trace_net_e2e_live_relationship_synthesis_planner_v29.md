# TRACE-Net E2E Live Relationship/Synthesis Planner v29

Quality status: **PASS**
Status: `E2E_LIVE_RELATIONSHIP_SYNTHESIS_PLANNER_READY`

## Summary
- exact_search_document_count: 1497
- page_summary_count: 509
- leiden_page_membership_count: 509
- endpoint_route_count: 4
- sample_query_count: 8
- sample_success_count: 8
- stage_timing_record_count: 8
- relationship_sample_count: 4
- relationship_guidance_sample_count: 4
- relationship_synthesis_sample_count: 2
- relationship_proof_violation_count: 0
- llm_called_sample_count: 0
- sample_avg_latency_ms: 3.293
- sample_avg_llm_ms: 0.001
- response_mode_counts: {'exact_single_value': 1, 'exact_missing_value': 1, 'capped_listing': 1, 'drilldown_request': 1, 'relationship_navigation': 2, 'relationship_synthesis': 2}
- relationship_mode: guarded
- llm_mode: simulate
- llm_model: gemma4:26b
- base_url_windows: http://127.0.0.1:8024/v1
- base_url_open_webui_docker: http://host.docker.internal:8024/v1
- answer_permission_count: 0
- source_truth_mutation_allowed_count: 0

## Contract
- v28 deterministic lookup/listing/drill-down remains the first path.
- Relationship/navigation/synthesis questions use graph/Leiden as guidance only.
- Source-truth seed evidence proves only the seed facts, not inferred relationships.
- The LLM may draft relationship synthesis, but TRACE-Net rebuilds/final-gates the answer.
- No raw 5TB scan, graph rebuild, OCR rerun, source-truth mutation, or service writes occur at query time.

## Sample query results
### Find part number 120-36833-503
- relationship_query: False
- response_mode: exact_single_value
- final_gate_status: LIVE_ORCHESTRATOR_FINAL_GATE_PASS
- llm_status: LLM_SKIPPED_DETERMINISTIC_PLANNER
- source_truth_seed_evidence_count: 
- relationship_guidance_count: 
- candidate_page_count: 
- total_request_ms: 12.274
- llm_draft_ms: 0.001
- final_answer_preview: TRACE-Net found part number 120-36833-503 on page t_p_120_1176_p000003 as covered_part_number [1]. The available direct source-truth evidence confirms the listing, but it does not provide enough information to describe the part physically.

### Find part number DOES-NOT-EXIST-999
- relationship_query: False
- response_mode: exact_missing_value
- final_gate_status: LIVE_ORCHESTRATOR_AUDIT_ONLY
- llm_status: LLM_SKIPPED_DETERMINISTIC_PLANNER
- source_truth_seed_evidence_count: 
- relationship_guidance_count: 
- candidate_page_count: 
- total_request_ms: 6.805
- llm_draft_ms: 0.0
- final_answer_preview: TRACE-Net did not find direct citation-ready source-truth evidence for this query. No source-truth claim is made. Try narrowing by part number, manual reference, page, or table text.

### What maintenance manual pages mention covered part numbers?
- relationship_query: False
- response_mode: capped_listing
- final_gate_status: LIVE_ORCHESTRATOR_FINAL_GATE_PASS
- llm_status: LLM_SKIPPED_DETERMINISTIC_PLANNER
- source_truth_seed_evidence_count: 
- relationship_guidance_count: 
- candidate_page_count: 
- total_request_ms: 1.937
- llm_draft_ms: 0.0
- final_answer_preview: TRACE-Net found covered part numbers on page(s) t_p_120_1176_p000003. Direct source-truth examples include 120-36833-001 [1]; 120-36833-003 [2]; 120-36833-005 [3]; 120-36833-501 [4]; 120-36833-503 [5]; 120-36833-507 [6]; 120-36833-509 [7]; 120-36833-511 [8]; 120-36833-513 [9]; 120-36833-515 [10]. Results were capped: TRACE-Net returned 10 of 150 matching records. Available drill-downs include document, manual, revision, section, route, field_type.

### Drill down covered part numbers by page
- relationship_query: False
- response_mode: drilldown_request
- final_gate_status: LIVE_ORCHESTRATOR_FINAL_GATE_PASS
- llm_status: LLM_SKIPPED_DETERMINISTIC_PLANNER
- source_truth_seed_evidence_count: 
- relationship_guidance_count: 
- candidate_page_count: 
- total_request_ms: 1.527
- llm_draft_ms: 0.0
- final_answer_preview: TRACE-Net drill-down by page: t_p_120_1176_p000003: 150. Direct source-truth examples include 120-36833-001 [1]; 120-36833-003 [2]; 120-36833-005 [3]; 120-36833-501 [4]; 120-36833-503 [5]; 120-36833-507 [6]; 120-36833-509 [7]; 120-36833-511 [8]; 120-36833-513 [9]; 120-36833-515 [10]. Results were capped: TRACE-Net returned 10 of 150 matching records. Available drill-downs include document, manual, revision, section, route, field_type.

### What pages are related to part number 120-36833-503?
- relationship_query: True
- response_mode: relationship_navigation
- final_gate_status: LIVE_RELATIONSHIP_FINAL_GATE_PASS
- llm_status: LLM_SKIPPED_RELATIONSHIP_NAVIGATION
- source_truth_seed_evidence_count: 1
- relationship_guidance_count: 1
- candidate_page_count: 3
- total_request_ms: 1.543
- llm_draft_ms: 0.001
- final_answer_preview: TRACE-Net found direct source-truth seed evidence on page(s) t_p_120_1176_p000003: 120-36833-503 [1]. Leiden/graph guidance places the seed page(s) in tracenet_community_00115; candidate pages for inspection include t_p_120_1176_p000003, t_p_120_1176_p000319, t_p_120_1176_p000320. Graph/Leiden output is guidance only, not proof. Confirm candidate pages with source-truth evidence before making a relationship claim.

### Which pages are in the same Leiden community as page t_p_120_1176_p000003?
- relationship_query: True
- response_mode: relationship_navigation
- final_gate_status: LIVE_RELATIONSHIP_FINAL_GATE_PASS
- llm_status: LLM_SKIPPED_RELATIONSHIP_NAVIGATION
- source_truth_seed_evidence_count: 0
- relationship_guidance_count: 1
- candidate_page_count: 3
- total_request_ms: 0.06
- llm_draft_ms: 0.001
- final_answer_preview: TRACE-Net is using the requested page ID as a graph-navigation seed. A page ID can seed navigation, but it is not by itself proof of a part/manual relationship. Leiden/graph guidance places the seed page(s) in tracenet_community_00115; candidate pages for inspection include t_p_120_1176_p000003, t_p_120_1176_p000319, t_p_120_1176_p000320. Graph/Leiden output is guidance only, not proof. Confirm candidate pages with source-truth evidence before making a relationship claim.

### Show graph neighbors for page t_p_120_1176_p000003
- relationship_query: True
- response_mode: relationship_synthesis
- final_gate_status: LIVE_RELATIONSHIP_FINAL_GATE_PASS
- llm_status: LLM_SIMULATED_RELATIONSHIP_DRAFT
- source_truth_seed_evidence_count: 0
- relationship_guidance_count: 1
- candidate_page_count: 3
- total_request_ms: 0.043
- llm_draft_ms: 0.001
- final_answer_preview: TRACE-Net is using the requested page ID as a graph-navigation seed. A page ID can seed navigation, but it is not by itself proof of a part/manual relationship. Leiden/graph guidance places the seed page(s) in tracenet_community_00115; candidate pages for inspection include t_p_120_1176_p000003, t_p_120_1176_p000319, t_p_120_1176_p000320. The available context can guide inspection, but it does not by itself prove a factual relationship between the entities unless a direct source-truth record sta

### Explain how part number 120-36833-503 relates to manual reference 25-21-00
- relationship_query: True
- response_mode: relationship_synthesis
- final_gate_status: LIVE_RELATIONSHIP_FINAL_GATE_PASS
- llm_status: LLM_SIMULATED_RELATIONSHIP_DRAFT
- source_truth_seed_evidence_count: 10
- relationship_guidance_count: 7
- candidate_page_count: 10
- total_request_ms: 2.155
- llm_draft_ms: 0.001
- final_answer_preview: TRACE-Net found direct source-truth seed evidence on page(s) t_p_120_1176_p000003, t_p_120_1176_p000005, t_p_120_1176_p000027, t_p_120_1176_p000028, t_p_120_1176_p000029, t_p_120_1176_p000030, t_p_120_1176_p000031: 120-36833-503 [1]; 25-21-00 [2]; 25-21-00 [3]; 25-21-00 [4]; 25-21 [5]. Leiden/graph guidance places the seed page(s) in tracenet_community_00115, tracenet_community_00037, tracenet_community_00038; candidate pages for inspection include t_p_120_1176_p000003, t_p_120_1176_p000319, t_p

## Quality checks
- PASS exact_search_document_count: observed=1497 expected=>= 10
- PASS endpoint_route_count: observed=4 expected=>= 4
- PASS sample_query_count: observed=8 expected=>= 8
- PASS sample_success_count: observed=8 expected=>= 8
- PASS stage_timing_record_count: observed=8 expected=>= 8
- PASS relationship_sample_count: observed=4 expected=>= 4
- PASS relationship_guidance_sample_count: observed=4 expected=>= 3
- PASS relationship_synthesis_sample_count: observed=2 expected=>= 1
- PASS relationship_proof_violation_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS contract_raw_5tb_scan_at_query_time: observed=False expected=is False
- PASS contract_graph_rebuild_at_query_time: observed=False expected=is False
- PASS contract_relationship_claims_require_source_truth: observed=True expected=is True
- PASS contract_graph_leiden_guidance_only: observed=True expected=is True
- PASS require_no_answer_permission: observed=0 expected=== 0

report_path: `local_data\organization\trace_net\e2e_live_relationship_synthesis_planner\trace_net_e2e_live_relationship_synthesis_planner_v29.json`
sample_jsonl_path: `local_data\organization\trace_net\e2e_live_relationship_synthesis_planner\trace_net_e2e_live_relationship_synthesis_planner_samples_v29.jsonl`
