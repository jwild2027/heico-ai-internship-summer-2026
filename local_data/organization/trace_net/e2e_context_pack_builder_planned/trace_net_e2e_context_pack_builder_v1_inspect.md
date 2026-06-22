# TRACE-Net E2E Context Pack Builder v1 Inspect

Quality status: **PASS**

## Purpose
This artifact converts ranked retrieval groups into context packs for the later final gate.
It is intentionally retrieval-only: context can be reviewed, cited, and ranked, but cannot answer directly.

## Context pack contract
- retrieval_permission: ranking_only_until_final_gate
- answer_authority: blocked
- ready_for_final_gate: True
- can_answer_directly: False
- can_prove_claims: False
- source_truth_mutation_allowed: False
- writes_to_postgres: False
- writes_to_qdrant: False
- writes_to_opensearch: False
- uploads_to_opensearch: False

## Main counters
- source_retrieval_group_count: 5
- context_pack_count: 5
- context_pack_with_items_count: 5
- total_context_item_count: 25
- page_with_context_item_count: 8
- field_count: 5
- citation_ready_context_item_count: 25
- source_trace_ready_context_item_count: 25
- schema_missing_required_key_item_count: 0

## Field counts
- covered_part_number: 10
- ipl_figure_item_or_quantity: 5
- ipl_part_number: 4
- ipl_text: 5
- manual_page_reference: 1

## Safety/write counters
- unsafe_context_record_count: 0
- answer_permission_count: 0
- can_answer_directly_count: 0
- can_prove_claims_count: 0
- source_truth_mutation_allowed_count: 0
- postgres_write_attempt_count: 0
- qdrant_write_attempt_count: 0
- opensearch_write_attempt_count: 0
- opensearch_upload_attempt_count: 0

## Context packs
- e2e_query_v1_0001 | covered_part_number | query='Find part number 120-36833-001' | items=5
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-001 | citation_ready=True | source_trace_ready=True
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-003 | citation_ready=True | source_trace_ready=True
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-005 | citation_ready=True | source_trace_ready=True
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-501 | citation_ready=True | source_trace_ready=True
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-503 | citation_ready=True | source_trace_ready=True
- e2e_query_v1_0002 | manual_page_reference | query='Where is manual reference 25-21-00 used?' | items=5
  - t_p_120_1176_p000005 | manual_page_reference | 25-21-00 | citation_ready=True | source_trace_ready=True
  - t_p_120_1176_p000027 | ipl_part_number | 25-21-00 | citation_ready=True | source_trace_ready=True
  - t_p_120_1176_p000028 | ipl_part_number | 25-21-00 | citation_ready=True | source_trace_ready=True
  - t_p_120_1176_p000029 | ipl_part_number | 25-21-00 | citation_ready=True | source_trace_ready=True
  - t_p_120_1176_p000030 | ipl_part_number | 25-21-00 | citation_ready=True | source_trace_ready=True
- e2e_query_v1_0003 | ipl_figure_item_or_quantity | query='Find IPL item 130' | items=5
  - t_p_120_1176_p000027 | ipl_figure_item_or_quantity | 130 | citation_ready=True | source_trace_ready=True
  - t_p_120_1176_p000028 | ipl_figure_item_or_quantity | 130 | citation_ready=True | source_trace_ready=True
  - t_p_120_1176_p000036 | ipl_figure_item_or_quantity | 130 | citation_ready=True | source_trace_ready=True
  - t_p_120_1176_p000027 | ipl_figure_item_or_quantity | 4 | citation_ready=True | source_trace_ready=True
  - t_p_120_1176_p000027 | ipl_figure_item_or_quantity | 70 | citation_ready=True | source_trace_ready=True
- e2e_query_v1_0004 | table_text | query='Search table text MAINTENANCE MANUAL WITH' | items=5
  - t_p_120_1176_p000027 | ipl_text | MAINTENANCE MANUAL WITH | citation_ready=True | source_trace_ready=True
  - t_p_120_1176_p000028 | ipl_text | MAINTENANCE MANUAL WITH | citation_ready=True | source_trace_ready=True
  - t_p_120_1176_p000029 | ipl_text | MAINTENANCE MANUAL WITH | citation_ready=True | source_trace_ready=True
  - t_p_120_1176_p000030 | ipl_text | MAINTENANCE MANUAL WITH | citation_ready=True | source_trace_ready=True
  - t_p_120_1176_p000031 | ipl_text | MAINTENANCE MANUAL WITH | citation_ready=True | source_trace_ready=True
- e2e_query_v1_0005 | covered_part_number | query='What maintenance manual pages mention covered part numbers?' | items=5
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-001 | citation_ready=True | source_trace_ready=True
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-003 | citation_ready=True | source_trace_ready=True
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-005 | citation_ready=True | source_trace_ready=True
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-501 | citation_ready=True | source_trace_ready=True
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-503 | citation_ready=True | source_trace_ready=True

## Quality checks
- PASS source_runtime_quality_pass: observed=True expected=is True
- PASS source_runtime_ready_for_context_pack: observed=True expected=is True
- PASS source_retrieval_group_count: observed=5 expected=>= 5
- PASS context_pack_count: observed=5 expected=>= 5
- PASS context_pack_with_items_count: observed=5 expected=>= 5
- PASS total_context_item_count: observed=25 expected=>= 20
- PASS page_with_context_item_count: observed=8 expected=>= 2
- PASS citation_ready_context_item_count: observed=25 expected=>= 20
- PASS source_trace_ready_context_item_count: observed=25 expected=>= 20
- PASS field_count: observed=5 expected=>= 3
- PASS schema_missing_required_key_item_count: observed=0 expected=== 0
- PASS unsafe_context_record_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS can_answer_directly_count: observed=0 expected=== 0
- PASS can_prove_claims_count: observed=0 expected=== 0
- PASS postgres_write_attempt_count: observed=0 expected=== 0
- PASS qdrant_write_attempt_count: observed=0 expected=== 0
- PASS opensearch_write_attempt_count: observed=0 expected=== 0
- PASS opensearch_upload_attempt_count: observed=0 expected=== 0
- PASS all_context_retrieval_only: observed=True expected=is True
