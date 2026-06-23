# TRACE-Net E2E Live WebUI Final-Gated Gemma Endpoint v24

Quality status: **PASS**
Status: `E2E_LIVE_WEBUI_FINAL_GATED_GEMMA_ENDPOINT_READY`

## Summary
- final_gate_count: 5
- final_answer_count: 5
- ready_final_answer_count: 5
- endpoint_route_count: 4
- final_answers_with_source_truth_citations_count: 5
- cap_disclosures_in_final_answers_count: 3
- unsupported_claim_count: 0
- final_non_direct_citation_marker_count: 0
- graph_proof_authority_violation_count: 0
- summary_proof_authority_violation_count: 0
- answer_permission_count: 0
- source_truth_mutation_allowed_count: 0
- base_url_windows: http://127.0.0.1:8020/v1
- base_url_open_webui_docker: http://host.docker.internal:8020/v1

## Contract
- This endpoint serves final-gated Gemma answers from the v23 artifact.
- It does not call Gemma at request time; v22 already produced drafts and v23 repaired/gated them.
- Source-truth evidence remains the only proof authority.
- Graph/Leiden and v2 summaries remain guidance only.
- Nearby OCR/table context is not direct proof for the user query.
- It does not scan raw 5TB data, rebuild the graph, mutate source truth, or write to services.

## Final-gated WebUI answers
### live_llm_final_gate_v23_0001 — ready=True
- query: Find part number 120-36834-509
- citation_like_count: 1
- has_cap_disclosure: False
- final_answer_preview: TRACE-Net found part number 120-36834-509 on page t_p_120_1176_p000003 as covered_part_number [1]. The available direct source-truth evidence confirms the listing, but it does not provide enough information to describe the part physically.

### live_llm_final_gate_v23_0002 — ready=True
- query: Find part number 120-36833-501
- citation_like_count: 1
- has_cap_disclosure: False
- final_answer_preview: TRACE-Net found part number 120-36833-501 on page t_p_120_1176_p000003 as covered_part_number [1]. The available direct source-truth evidence confirms the listing, but it does not provide enough information to describe the part physically.

### live_llm_final_gate_v23_0003 — ready=True
- query: What maintenance manual pages mention covered part numbers?
- citation_like_count: 10
- has_cap_disclosure: True
- final_answer_preview: TRACE-Net found covered part numbers on page(s) t_p_120_1176_p000003. Direct source-truth examples include 120-36833-001 [1]; 120-36833-003 [2]; 120-36833-005 [3]; 120-36833-501 [4]; 120-36833-503 [5]; 120-36833-507 [6]; 120-36833-509 [7]; 120-36833-511 [8]; 120-36833-513 [9]; 120-36833-515 [10]. Results were capped: TRACE-Net returned 10 of 150 matching records. Available drill-downs include document, manual, revision, section, route, field_type.

### live_llm_final_gate_v23_0004 — ready=True
- query: Where is manual reference 25-21-00 used?
- citation_like_count: 1
- has_cap_disclosure: True
- final_answer_preview: TRACE-Net found manual reference 25-21-00 on page t_p_120_1176_p000005 [1]. The same page/value was collapsed from 10 repeated source records. Results were capped: TRACE-Net returned 10 of 50 matching records. Available drill-downs include document, manual, revision, section, route, field_type.

### live_llm_final_gate_v23_0005 — ready=True
- query: Search table text MAINTENANCE MANUAL WITH
- citation_like_count: 1
- has_cap_disclosure: True
- final_answer_preview: TRACE-Net found the exact table text "MAINTENANCE MANUAL WITH" on page t_p_120_1176_p000027 [1]. Nearby OCR/table records were returned as context only and are not treated as direct proof for this query. Results were capped: TRACE-Net returned 10 of 188 matching records. Available drill-downs include document, manual, revision, section, route, field_type.

## Quality checks
- PASS final_gate_count: observed=5 expected=>= 5
- PASS ready_final_answer_count: observed=5 expected=>= 5
- PASS endpoint_route_count: observed=4 expected=>= 4
- PASS final_answers_with_source_truth_citations_count: observed=5 expected=>= 5
- PASS cap_disclosures_in_final_answers_count: observed=3 expected=>= 3
- PASS unsupported_claim_count: observed=0 expected=<= 0
- PASS final_non_direct_citation_marker_count: observed=0 expected=<= 0
- PASS graph_proof_authority_violation_count: observed=0 expected=<= 0
- PASS summary_proof_authority_violation_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS require_no_answer_permission: observed=0 expected=== 0
