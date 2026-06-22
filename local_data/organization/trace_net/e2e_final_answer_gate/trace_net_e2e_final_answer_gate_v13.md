# TRACE-Net E2E Final Answer Gate v13

Quality status: **FAIL**
Status: `E2E_FINAL_ANSWER_GATE_NEEDS_REPAIR`

## Contract
This stage validates reasoned response drafts before WebUI final-answer integration. It does not call an LLM, rerun retrieval, rerun OCR, rebuild embeddings, rebuild graph, rerun table extraction, mutate source truth, or write to services.

## Summary
- reasoned_draft_count: 5
- final_gate_count: 5
- passed_final_gate_count: 4
- blocked_final_gate_count: 1
- citation_supported_answer_count: 4
- total_citation_count: 25
- answers_with_limitations_count: 5
- final_answers_ready_for_webui_count: 4
- unsupported_claim_count: 1
- graph_summary_proof_violation_count: 0
- answer_permission_count: 0
- source_truth_mutation_allowed_count: 0

## Final-gated answers
- **FINAL_ANSWER_GATE_PASSED** `final_answer_gate_v13_0001` | covered_part_number | Find part number 120-36833-001 | citations=5
  - TRACE-Net found part number 120-36833-001 as a covered part number on page t_p_120_1176_p000003 [1]. The same evidence set also includes related covered part numbers: 120-36833-003 [2], 120-36833-005 [3]. The evidence is sufficient to confirm the listing, b...
- **FINAL_ANSWER_GATE_PASSED** `final_answer_gate_v13_0002` | covered_part_number | Find part number 120-36834-509 | citations=5
  - TRACE-Net found part number 120-36834-509 as a covered part number on page t_p_120_1176_p000003 [1]. The same evidence set also includes related covered part numbers: 120-36833-001 [2], 120-36833-003 [3]. The evidence is sufficient to confirm the listing, b...
- **FINAL_ANSWER_GATE_PASSED** `final_answer_gate_v13_0003` | manual_page_reference | Where is manual reference 25-21-00 used? | citations=5
  - TRACE-Net found the manual reference in these source-truth records: manual_page_reference=25-21-00 on page t_p_120_1176_p000005 [1]; ipl_part_number=25-21-00 on page t_p_120_1176_p000027 [2]; ipl_part_number=25-21-00 on page t_p_120_1176_p000028 [3]; ipl_pa...
- **FINAL_ANSWER_GATE_PASSED** `final_answer_gate_v13_0004` | table_text | Search table text MAINTENANCE MANUAL WITH | citations=5
  - TRACE-Net found the table text 'MAINTENANCE MANUAL WITH' on page(s) t_p_120_1176_p000027 [1], t_p_120_1176_p000028 [2], t_p_120_1176_p000029 [3], t_p_120_1176_p000030 [4], t_p_120_1176_p000031 [5].
- **FINAL_ANSWER_GATE_BLOCKED** `final_answer_gate_v13_0005` | covered_part_number | What maintenance manual pages mention covered part numbers? | citations=5
  - TRACE-Net found covered part numbers on page(s) t_p_120_1176_p000003. Examples from the source-truth evidence include 120-36833-001 [1], 120-36833-003 [2], 120-36833-005 [3].

## Quality checks
- PASS quality_status: observed=PASS expected=== PASS
- PASS reasoned_draft_count: observed=5 expected=>= 5
- PASS final_gate_count: observed=5 expected=>= 5
- FAIL passed_final_gate_count: observed=4 expected=>= 5
- FAIL citation_supported_answer_count: observed=4 expected=>= 5
- PASS total_citation_count: observed=25 expected=>= 15
- FAIL final_answers_ready_for_webui_count: observed=4 expected=>= 5
- PASS answers_with_limitations_count: observed=5 expected=>= 5
- FAIL unsupported_claim_count: observed=1 expected=<= 0
- PASS graph_summary_proof_violation_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS contract_can_answer_directly: observed=0 expected=== 0
- PASS contract_can_prove_claims: observed=0 expected=== 0
- PASS postgres_write_attempt_count: observed=0 expected=== 0
- PASS qdrant_write_attempt_count: observed=0 expected=== 0
- PASS opensearch_write_attempt_count: observed=0 expected=== 0
- PASS require_no_answer_permission: observed=0 expected=== 0
