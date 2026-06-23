# TRACE-Net E2E Executed Plan Context Pack v19

Quality status: **PASS**
Status: `E2E_EXECUTED_PLAN_CONTEXT_PACK_READY_FOR_LIVE_SELF_RAG`

## Summary
- context_pack_count: 5
- ready_context_pack_count: 5
- total_source_truth_evidence_count: 32
- packs_with_evidence_box_count: 5
- packs_with_guidance_box_count: 5
- packs_with_graph_guidance_count: 5
- packs_with_v2_summary_guidance_count: 5
- packs_with_answer_rules_count: 5
- packs_with_aggregation_or_cap_disclosure_count: 5
- capped_result_disclosure_count: 3
- graph_proof_authority_violation_count: 0
- summary_proof_authority_violation_count: 0
- answer_permission_count: 0
- source_truth_mutation_allowed_count: 0

## Contract
- Source-truth evidence is the only proof authority for final claims.
- Leiden/community graph guidance is navigation guidance only, not proof.
- v2 summaries are guidance only, not proof.
- High-degree or capped result sets must disclose total vs returned counts and drill-down options.
- The LLM reads compact context packs only; query-time processing does not scan the raw 5TB corpus or rebuild the graph.

## Context packs
### context_pack_v19_0001 — `part_number`
- query: Find part number 120-36834-509
- status: `CONTEXT_PACK_READY_FOR_SELF_RAG`
- source_truth_evidence_items: 1
- total_match_count: 1
- returned_match_count: 1
- result_was_capped: False
- more_results_available: False

### context_pack_v19_0002 — `part_number`
- query: Find part number 120-36833-501
- status: `CONTEXT_PACK_READY_FOR_SELF_RAG`
- source_truth_evidence_items: 1
- total_match_count: 1
- returned_match_count: 1
- result_was_capped: False
- more_results_available: False

### context_pack_v19_0003 — `covered_part_number`
- query: What maintenance manual pages mention covered part numbers?
- status: `CONTEXT_PACK_READY_FOR_SELF_RAG`
- source_truth_evidence_items: 10
- total_match_count: 150
- returned_match_count: 10
- result_was_capped: True
- more_results_available: True

### context_pack_v19_0004 — `manual_page_reference`
- query: Where is manual reference 25-21-00 used?
- status: `CONTEXT_PACK_READY_FOR_SELF_RAG`
- source_truth_evidence_items: 10
- total_match_count: 50
- returned_match_count: 10
- result_was_capped: True
- more_results_available: True

### context_pack_v19_0005 — `table_text`
- query: Search table text MAINTENANCE MANUAL WITH
- status: `CONTEXT_PACK_READY_FOR_SELF_RAG`
- source_truth_evidence_items: 10
- total_match_count: 188
- returned_match_count: 10
- result_was_capped: True
- more_results_available: True

## Quality checks
- PASS context_pack_count: observed=5 expected=>= 5
- PASS ready_context_pack_count: observed=5 expected=>= 5
- PASS total_source_truth_evidence_count: observed=32 expected=>= 10
- PASS packs_with_evidence_box_count: observed=5 expected=>= 5
- PASS packs_with_guidance_box_count: observed=5 expected=>= 5
- PASS packs_with_graph_guidance_count: observed=5 expected=>= 5
- PASS packs_with_v2_summary_guidance_count: observed=5 expected=>= 0
- PASS packs_with_answer_rules_count: observed=5 expected=>= 5
- PASS packs_with_aggregation_or_cap_disclosure_count: observed=5 expected=>= 5
- PASS graph_proof_authority_violation_count: observed=0 expected=<= 0
- PASS summary_proof_authority_violation_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS require_no_answer_permission: observed=0 expected=== 0
