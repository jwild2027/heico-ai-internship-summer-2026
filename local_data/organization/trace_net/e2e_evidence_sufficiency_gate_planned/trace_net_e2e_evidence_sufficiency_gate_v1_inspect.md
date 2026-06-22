# TRACE-Net E2E Evidence Sufficiency Gate v1 Inspect

Quality status: **PASS**

## Purpose
This artifact checks whether each retrieval-only context pack has enough citation/source-trace-ready evidence for final-gate review.
It does not answer, prove claims, mutate source truth, or write to runtime services.

## Evidence sufficiency contract
- retrieval_permission: ranking_only_until_final_gate
- answer_authority: blocked_until_final_gate
- ready_for_final_gate_smoke: True
- sufficiency_means: ready_for_final_gate_review_not_answer_permission
- can_answer_directly: False
- can_prove_claims: False
- source_truth_mutation_allowed: False
- writes_to_postgres: False
- writes_to_qdrant: False
- writes_to_opensearch: False
- uploads_to_opensearch: False

## Main counters
- source_context_pack_count: 5
- evidence_sufficiency_gate_record_count: 5
- sufficient_context_pack_count: 5
- audit_only_context_pack_count: 0
- final_gate_review_ready_pack_count: 5
- total_evidence_item_count: 25
- citation_ready_evidence_item_count: 25
- source_trace_ready_evidence_item_count: 25
- page_with_evidence_item_count: 8
- field_count: 5
- schema_missing_required_key_item_count: 0

## Field counts
- covered_part_number: 10
- ipl_figure_item_or_quantity: 5
- ipl_part_number: 4
- ipl_text: 5
- manual_page_reference: 1

## Safety/write counters
- unsafe_evidence_sufficiency_record_count: 0
- answer_permission_count: 0
- can_answer_directly_count: 0
- can_prove_claims_count: 0
- source_truth_mutation_allowed_count: 0
- postgres_write_attempt_count: 0
- qdrant_write_attempt_count: 0
- opensearch_write_attempt_count: 0
- opensearch_upload_attempt_count: 0

## Gate records
- e2e_query_v1_0001 | covered_part_number | EVIDENCE_SUFFICIENT_FOR_FINAL_GATE_REVIEW | items=5 pages=t_p_120_1176_p000003
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-001 | citation_ready=True | source_trace_ready=True
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-003 | citation_ready=True | source_trace_ready=True
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-005 | citation_ready=True | source_trace_ready=True
- e2e_query_v1_0002 | manual_page_reference | EVIDENCE_SUFFICIENT_FOR_FINAL_GATE_REVIEW | items=5 pages=t_p_120_1176_p000005,t_p_120_1176_p000027,t_p_120_1176_p000028,t_p_120_1176_p000029,t_p_120_1176_p000030
  - t_p_120_1176_p000005 | manual_page_reference | 25-21-00 | citation_ready=True | source_trace_ready=True
  - t_p_120_1176_p000027 | ipl_part_number | 25-21-00 | citation_ready=True | source_trace_ready=True
  - t_p_120_1176_p000028 | ipl_part_number | 25-21-00 | citation_ready=True | source_trace_ready=True
- e2e_query_v1_0003 | ipl_figure_item_or_quantity | EVIDENCE_SUFFICIENT_FOR_FINAL_GATE_REVIEW | items=5 pages=t_p_120_1176_p000027,t_p_120_1176_p000028,t_p_120_1176_p000036
  - t_p_120_1176_p000027 | ipl_figure_item_or_quantity | 130 | citation_ready=True | source_trace_ready=True
  - t_p_120_1176_p000028 | ipl_figure_item_or_quantity | 130 | citation_ready=True | source_trace_ready=True
  - t_p_120_1176_p000036 | ipl_figure_item_or_quantity | 130 | citation_ready=True | source_trace_ready=True
- e2e_query_v1_0004 | table_text | EVIDENCE_SUFFICIENT_FOR_FINAL_GATE_REVIEW | items=5 pages=t_p_120_1176_p000027,t_p_120_1176_p000028,t_p_120_1176_p000029,t_p_120_1176_p000030,t_p_120_1176_p000031
  - t_p_120_1176_p000027 | ipl_text | MAINTENANCE MANUAL WITH | citation_ready=True | source_trace_ready=True
  - t_p_120_1176_p000028 | ipl_text | MAINTENANCE MANUAL WITH | citation_ready=True | source_trace_ready=True
  - t_p_120_1176_p000029 | ipl_text | MAINTENANCE MANUAL WITH | citation_ready=True | source_trace_ready=True
- e2e_query_v1_0005 | covered_part_number | EVIDENCE_SUFFICIENT_FOR_FINAL_GATE_REVIEW | items=5 pages=t_p_120_1176_p000003
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-001 | citation_ready=True | source_trace_ready=True
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-003 | citation_ready=True | source_trace_ready=True
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-005 | citation_ready=True | source_trace_ready=True

## Quality checks
- PASS source_context_pack_quality_pass: observed=True expected=is True
- PASS source_context_pack_ready_for_final_gate: observed=True expected=is True
- PASS source_context_pack_count: observed=5 expected=>= 5
- PASS source_context_pack_with_items_count: observed=5 expected=>= 5
- PASS evidence_sufficiency_gate_record_count: observed=5 expected=>= 5
- PASS sufficient_context_pack_count: observed=5 expected=>= 4
- PASS final_gate_review_ready_pack_count: observed=5 expected=>= 4
- PASS total_evidence_item_count: observed=25 expected=>= 20
- PASS citation_ready_evidence_item_count: observed=25 expected=>= 20
- PASS source_trace_ready_evidence_item_count: observed=25 expected=>= 20
- PASS page_with_evidence_item_count: observed=8 expected=>= 2
- PASS field_count: observed=5 expected=>= 3
- PASS schema_missing_required_key_item_count: observed=0 expected=== 0
- PASS unsafe_evidence_sufficiency_record_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS can_answer_directly_count: observed=0 expected=== 0
- PASS can_prove_claims_count: observed=0 expected=== 0
- PASS postgres_write_attempt_count: observed=0 expected=== 0
- PASS qdrant_write_attempt_count: observed=0 expected=== 0
- PASS opensearch_write_attempt_count: observed=0 expected=== 0
- PASS opensearch_upload_attempt_count: observed=0 expected=== 0
- PASS all_gate_records_no_answer_authority: observed=True expected=is True
