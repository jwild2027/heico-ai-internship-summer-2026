# TRACE-Net E2E Live LLM Final Gate v23

Quality status: **PASS**
Status: `E2E_LIVE_LLM_FINAL_GATE_READY_FOR_WEBUI`

## Summary
- llm_draft_count: 5
- final_gate_count: 5
- passed_final_gate_count: 5
- final_answers_ready_for_webui_count: 5
- repaired_final_answer_count: 5
- final_answers_with_source_truth_citations_count: 5
- draft_v2_summary_proof_violation_count: 1
- draft_nearby_context_overstatement_count: 1
- draft_non_direct_citation_marker_count: 3
- cap_disclosure_required_count: 3
- cap_disclosures_in_final_answers_count: 3
- unsupported_claim_count: 0
- final_non_direct_citation_marker_count: 0
- graph_proof_authority_violation_count: 0
- summary_proof_authority_violation_count: 0
- answer_permission_count: 0
- source_truth_mutation_allowed_count: 0

## Contract
- This gate does not call an LLM; it validates and repairs live LLM drafts.
- Source-truth evidence remains the only proof authority.
- Graph/Leiden and v2 summaries remain guidance only.
- Nearby source-truth context is not treated as direct proof for the query.
- Capped/high-degree results must be disclosed in final answers.

## Final answers
### live_llm_final_gate_v23_0001 — `LIVE_LLM_FINAL_GATE_PASS`
- query: Find part number 120-36834-509
- repaired_from_draft: True
- draft_v2_summary_proof_violation: False
- draft_nearby_context_overstatement: False
- non_direct_citation_marker_count: 0
- final_answer_preview: TRACE-Net found part number 120-36834-509 on page t_p_120_1176_p000003 as covered_part_number [1]. The available direct source-truth evidence confirms the listing, but it does not provide enough information to describe the part physically.

### live_llm_final_gate_v23_0002 — `LIVE_LLM_FINAL_GATE_PASS`
- query: Find part number 120-36833-501
- repaired_from_draft: True
- draft_v2_summary_proof_violation: False
- draft_nearby_context_overstatement: False
- non_direct_citation_marker_count: 0
- final_answer_preview: TRACE-Net found part number 120-36833-501 on page t_p_120_1176_p000003 as covered_part_number [1]. The available direct source-truth evidence confirms the listing, but it does not provide enough information to describe the part physically.

### live_llm_final_gate_v23_0003 — `LIVE_LLM_FINAL_GATE_PASS`
- query: What maintenance manual pages mention covered part numbers?
- repaired_from_draft: True
- draft_v2_summary_proof_violation: False
- draft_nearby_context_overstatement: False
- non_direct_citation_marker_count: 0
- final_answer_preview: TRACE-Net found covered part numbers on page(s) t_p_120_1176_p000003. Direct source-truth examples include 120-36833-001 [1]; 120-36833-003 [2]; 120-36833-005 [3]; 120-36833-501 [4]; 120-36833-503 [5]; 120-36833-507 [6]; 120-36833-509 [7]; 120-36833-511 [8]; 120-36833-513 [9]; 120-36833-515 [10]. Results were capped: TRACE-Net returned 10 of 150 matching rec

### live_llm_final_gate_v23_0004 — `LIVE_LLM_FINAL_GATE_PASS`
- query: Where is manual reference 25-21-00 used?
- repaired_from_draft: True
- draft_v2_summary_proof_violation: True
- draft_nearby_context_overstatement: False
- non_direct_citation_marker_count: 0
- final_answer_preview: TRACE-Net found manual reference 25-21-00 on page t_p_120_1176_p000005 [1]. The same page/value was collapsed from 10 repeated source records. Results were capped: TRACE-Net returned 10 of 50 matching records. Available drill-downs include document, manual, revision, section, route, field_type.

### live_llm_final_gate_v23_0005 — `LIVE_LLM_FINAL_GATE_PASS`
- query: Search table text MAINTENANCE MANUAL WITH
- repaired_from_draft: True
- draft_v2_summary_proof_violation: False
- draft_nearby_context_overstatement: True
- non_direct_citation_marker_count: 3
- final_answer_preview: TRACE-Net found the exact table text "MAINTENANCE MANUAL WITH" on page t_p_120_1176_p000027 [1]. Nearby OCR/table records were returned as context only and are not treated as direct proof for this query. Results were capped: TRACE-Net returned 10 of 188 matching records. Available drill-downs include document, manual, revision, section, route, field_type.

## Quality checks
- PASS llm_draft_count: observed=5 expected=>= 5
- PASS final_gate_count: observed=5 expected=>= 5
- PASS passed_final_gate_count: observed=5 expected=>= 5
- PASS final_answers_ready_for_webui_count: observed=5 expected=>= 5
- PASS repaired_final_answer_count: observed=5 expected=>= 5
- PASS final_answers_with_source_truth_citations_count: observed=5 expected=>= 5
- PASS cap_disclosures_in_final_answers_count: observed=3 expected=>= 3
- PASS unsupported_claim_count: observed=0 expected=<= 0
- PASS final_non_direct_citation_marker_count: observed=0 expected=<= 0
- PASS graph_proof_authority_violation_count: observed=0 expected=<= 0
- PASS summary_proof_authority_violation_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS require_no_answer_permission: observed=0 expected=== 0
