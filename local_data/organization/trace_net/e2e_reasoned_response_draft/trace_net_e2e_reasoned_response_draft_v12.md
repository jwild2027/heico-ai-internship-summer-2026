# TRACE-Net E2E Reasoned Response Draft v12

Quality status: **PASS**
Status: `E2E_REASONED_RESPONSE_DRAFT_READY_FOR_FINAL_GATE`

## Contract
This stage creates deterministic reasoned answer drafts from v11 prompt contracts. It does not call an LLM, rerun retrieval, rerun OCR, rebuild embeddings, rebuild graph, rerun table extraction, mutate source truth, or write to services.

## Summary
- prompt_contract_count: 5
- reasoned_draft_count: 5
- ready_reasoned_draft_count: 5
- drafts_ready_for_final_gate_count: 5
- audit_only_draft_count: 0
- total_citation_count: 25
- drafts_with_limitations_count: 5
- graph_summary_proof_violation_count: 0
- answer_permission_count: 0
- source_truth_mutation_allowed_count: 0

## Drafts
- **REASONED_RESPONSE_DRAFT_READY_FOR_FINAL_GATE** `reasoned_response_draft_v12_0001` | covered_part_number | Find part number 120-36833-001 | citations=5
  - TRACE-Net found part number 120-36833-001 as a covered part number on page t_p_120_1176_p000003 [1]. The same evidence set also includes related covered part numbers: 120-36833-003 [2], 120-36833-005 [3]. The evidence is sufficient to confirm the listing, but not enough to describe what the part physically is.
- **REASONED_RESPONSE_DRAFT_READY_FOR_FINAL_GATE** `reasoned_response_draft_v12_0002` | covered_part_number | Find part number 120-36834-509 | citations=5
  - TRACE-Net found part number 120-36834-509 as a covered part number on page t_p_120_1176_p000003 [1]. The same evidence set also includes related covered part numbers: 120-36833-001 [2], 120-36833-003 [3]. The evidence is sufficient to confirm the listing, but not enough to describe what the part physically is.
- **REASONED_RESPONSE_DRAFT_READY_FOR_FINAL_GATE** `reasoned_response_draft_v12_0003` | manual_page_reference | Where is manual reference 25-21-00 used? | citations=5
  - TRACE-Net found the manual reference in these source-truth records: manual_page_reference=25-21-00 on page t_p_120_1176_p000005 [1]; ipl_part_number=25-21-00 on page t_p_120_1176_p000027 [2]; ipl_part_number=25-21-00 on page t_p_120_1176_p000028 [3]; ipl_part_number=25-21-00 on page t_p_120_1176_p000029 [4]; ipl_part_number=25-21-00 on page t_p_120_1176_p000030 [5].
- **REASONED_RESPONSE_DRAFT_READY_FOR_FINAL_GATE** `reasoned_response_draft_v12_0004` | table_text | Search table text MAINTENANCE MANUAL WITH | citations=5
  - TRACE-Net found the table text 'MAINTENANCE MANUAL WITH' on page(s) t_p_120_1176_p000027 [1], t_p_120_1176_p000028 [2], t_p_120_1176_p000029 [3], t_p_120_1176_p000030 [4], t_p_120_1176_p000031 [5].
- **REASONED_RESPONSE_DRAFT_READY_FOR_FINAL_GATE** `reasoned_response_draft_v12_0005` | covered_part_number | What maintenance manual pages mention covered part numbers? | citations=5
  - TRACE-Net found covered part numbers on page(s) t_p_120_1176_p000003. Examples from the source-truth evidence include 120-36833-001 [1], 120-36833-003 [2], 120-36833-005 [3].

## Quality checks
- PASS quality_status: observed=PASS expected=== PASS
- PASS prompt_contract_count: observed=5 expected=>= 5
- PASS reasoned_draft_count: observed=5 expected=>= 5
- PASS ready_reasoned_draft_count: observed=5 expected=>= 5
- PASS total_citation_count: observed=25 expected=>= 15
- PASS drafts_with_limitations_count: observed=5 expected=>= 5
- PASS drafts_ready_for_final_gate_count: observed=5 expected=>= 5
- PASS graph_summary_proof_violation_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS contract_reasoned_draft_does_not_call_llm: observed=True expected=is True
- PASS contract_can_answer_directly: observed=0 expected=== 0
- PASS contract_can_prove_claims: observed=0 expected=== 0
- PASS postgres_write_attempt_count: observed=0 expected=== 0
- PASS qdrant_write_attempt_count: observed=0 expected=== 0
- PASS opensearch_write_attempt_count: observed=0 expected=== 0
