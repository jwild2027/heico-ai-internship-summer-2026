# TRACE-Net E2E Hybrid Retrieval Runtime v1 Inspect

Quality status: **PASS**

## Purpose
This artifact consumes safe E2E query-plan records and produces ranked retrieval groups.
It does not answer, prove claims, mutate source truth, or write to runtime services.

## Runtime contract
- retrieval_permission: ranking_only_until_final_gate
- answer_authority: blocked
- ready_for_context_pack: True
- can_answer_directly: False
- can_prove_claims: False
- source_truth_mutation_allowed: False
- writes_to_postgres: False
- writes_to_qdrant: False
- writes_to_opensearch: False
- uploads_to_opensearch: False

## Main counters
- source_query_input_record_count: 5
- source_bridge_record_count: 1497
- source_query_bridge_group_count: 6
- hybrid_retrieval_query_count: 5
- successful_retrieval_query_count: 5
- retrieval_group_count: 5
- total_retrieval_hit_count: 50
- page_with_retrieval_hit_count: 12
- field_count: 5

## Field counts
- covered_part_number: 20
- ipl_figure_item_or_quantity: 10
- ipl_part_number: 9
- ipl_text: 10
- manual_page_reference: 1

## Safety/write counters
- unsafe_runtime_record_count: 0
- answer_permission_count: 0
- can_answer_directly_count: 0
- can_prove_claims_count: 0
- source_truth_mutation_allowed_count: 0
- postgres_write_attempt_count: 0
- qdrant_write_attempt_count: 0
- opensearch_write_attempt_count: 0
- opensearch_upload_attempt_count: 0

## Retrieval groups
- e2e_query_v1_0001 | covered_part_number | query='Find part number 120-36833-001' | status=RETRIEVAL_MATCHED | hits=10
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-001 | score=988.2 | boost=1.35
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-003 | score=567.0 | boost=1.35
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-005 | score=567.0 | boost=1.35
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-501 | score=567.0 | boost=1.35
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-503 | score=567.0 | boost=1.35
- e2e_query_v1_0002 | manual_page_reference | query='Where is manual reference 25-21-00 used?' | status=RETRIEVAL_MATCHED | hits=10
  - t_p_120_1176_p000005 | manual_page_reference | 25-21-00 | score=1290.0 | boost=1.25
  - t_p_120_1176_p000027 | ipl_part_number | 25-21-00 | score=795.6 | boost=1.3
  - t_p_120_1176_p000028 | ipl_part_number | 25-21-00 | score=795.6 | boost=1.3
  - t_p_120_1176_p000029 | ipl_part_number | 25-21-00 | score=795.6 | boost=1.3
  - t_p_120_1176_p000030 | ipl_part_number | 25-21-00 | score=795.6 | boost=1.3
- e2e_query_v1_0003 | ipl_figure_item_or_quantity | query='Find IPL item 130' | status=RETRIEVAL_MATCHED | hits=10
  - t_p_120_1176_p000027 | ipl_figure_item_or_quantity | 130 | score=695.4 | boost=0.95
  - t_p_120_1176_p000028 | ipl_figure_item_or_quantity | 130 | score=695.4 | boost=0.95
  - t_p_120_1176_p000036 | ipl_figure_item_or_quantity | 130 | score=695.4 | boost=0.95
  - t_p_120_1176_p000027 | ipl_figure_item_or_quantity | 4 | score=399.0 | boost=0.95
  - t_p_120_1176_p000027 | ipl_figure_item_or_quantity | 70 | score=399.0 | boost=0.95
- e2e_query_v1_0004 | table_text | query='Search table text MAINTENANCE MANUAL WITH' | status=RETRIEVAL_MATCHED | hits=10
  - t_p_120_1176_p000027 | ipl_text | MAINTENANCE MANUAL WITH | score=420.0 | boost=1.0
  - t_p_120_1176_p000028 | ipl_text | MAINTENANCE MANUAL WITH | score=420.0 | boost=1.0
  - t_p_120_1176_p000029 | ipl_text | MAINTENANCE MANUAL WITH | score=420.0 | boost=1.0
  - t_p_120_1176_p000030 | ipl_text | MAINTENANCE MANUAL WITH | score=420.0 | boost=1.0
  - t_p_120_1176_p000031 | ipl_text | MAINTENANCE MANUAL WITH | score=420.0 | boost=1.0
- e2e_query_v1_0005 | covered_part_number | query='What maintenance manual pages mention covered part numbers?' | status=RETRIEVAL_MATCHED | hits=10
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-001 | score=567.0 | boost=1.35
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-003 | score=567.0 | boost=1.35
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-005 | score=567.0 | boost=1.35
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-501 | score=567.0 | boost=1.35
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-503 | score=567.0 | boost=1.35

## Quality checks
- PASS source_query_input_record_count: observed=5 expected=>= 5
- PASS source_bridge_record_count: observed=1497 expected=>= 1000
- PASS hybrid_retrieval_query_count: observed=5 expected=>= 5
- PASS successful_retrieval_query_count: observed=5 expected=>= 4
- PASS retrieval_group_count: observed=5 expected=>= 5
- PASS total_retrieval_hit_count: observed=50 expected=>= 10
- PASS page_with_retrieval_hit_count: observed=12 expected=>= 2
- PASS field_count: observed=5 expected=>= 3
- PASS unsafe_runtime_record_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS can_answer_directly_count: observed=0 expected=== 0
- PASS can_prove_claims_count: observed=0 expected=== 0
- PASS postgres_write_attempt_count: observed=0 expected=== 0
- PASS qdrant_write_attempt_count: observed=0 expected=== 0
- PASS opensearch_write_attempt_count: observed=0 expected=== 0
- PASS opensearch_upload_attempt_count: observed=0 expected=== 0
- PASS source_query_input_quality_pass: observed=True expected=is True
- PASS source_bridge_quality_pass: observed=True expected=is True
- PASS all_results_retrieval_only: observed=True expected=is True
