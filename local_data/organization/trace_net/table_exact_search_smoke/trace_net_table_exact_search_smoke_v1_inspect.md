# TRACE-Net Table Exact-Search Smoke v1 Inspect

Quality status: **PASS**

## Smoke counters
- source_exact_search_document_count: 1497
- smoke_query_count: 6
- successful_smoke_query_count: 6
- total_match_count: 42
- page_with_smoke_match_count: 12

## Safety/write counters
- unsafe_smoke_result_count: 0
- answer_permission_count: 0
- can_answer_directly_count: 0
- can_prove_claims_count: 0
- source_truth_mutation_allowed_count: 0
- postgres_write_attempt_count: 0
- qdrant_write_attempt_count: 0
- opensearch_write_attempt_count: 0
- opensearch_upload_attempt_count: 0

## Queries
- query='120-36833-001' matches=1
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-001 | score=185
- query='25-21-00' matches=10
  - t_p_120_1176_p000005 | manual_page_reference | 25-21-00 | score=185
  - t_p_120_1176_p000005 | manual_page_reference | 25-21-00 | score=185
  - t_p_120_1176_p000005 | manual_page_reference | 25-21-00 | score=185
  - t_p_120_1176_p000005 | manual_page_reference | 25-21-00 | score=185
  - t_p_120_1176_p000005 | manual_page_reference | 25-21-00 | score=185
- query='607' matches=1
  - t_p_120_1176_p000005 | page_rev_or_sequence_value | 607 | score=185
- query='MAINTENANCE MANUAL WITH' matches=10
  - t_p_120_1176_p000027 | ipl_text | MAINTENANCE MANUAL WITH | score=205
  - t_p_120_1176_p000028 | ipl_text | MAINTENANCE MANUAL WITH | score=205
  - t_p_120_1176_p000029 | ipl_text | MAINTENANCE MANUAL WITH | score=205
  - t_p_120_1176_p000030 | ipl_text | MAINTENANCE MANUAL WITH | score=205
  - t_p_120_1176_p000031 | ipl_text | MAINTENANCE MANUAL WITH | score=205
- query='130' matches=10
  - t_p_120_1176_p000027 | ipl_figure_item_or_quantity | 130 | score=185
  - t_p_120_1176_p000027 | ipl_figure_item_or_quantity | 130 | score=185
  - t_p_120_1176_p000027 | ipl_figure_item_or_quantity | 130 | score=185
  - t_p_120_1176_p000027 | ipl_figure_item_or_quantity | 130 | score=185
  - t_p_120_1176_p000027 | ipl_figure_item_or_quantity | 130 | score=185
- query='covered_part_number' matches=10
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-001 | score=160
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-003 | score=160
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-005 | score=160
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-501 | score=160
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-503 | score=160
