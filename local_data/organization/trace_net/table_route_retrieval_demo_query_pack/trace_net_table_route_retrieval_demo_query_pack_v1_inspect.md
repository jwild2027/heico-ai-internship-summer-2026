# TRACE-Net Table Route Retrieval Demo Query Pack v1 Inspect

Quality status: **PASS**

## Demo purpose
This artifact shows example table-route queries, the matched table values/pages, and the retrieval boost behavior.
It is intentionally retrieval-only: the table values can help find evidence, but cannot answer directly.

## Readiness contract
- source_retrieval_readiness_status: READY_FOR_RETRIEVAL_RANKING_ONLY
- demo_readiness_status: DEMO_READY_RETRIEVAL_ONLY
- retrieval_permission: ranking_only
- answer_authority: blocked
- ready_for_hybrid_retrieval_ranking: True
- ready_for_live_opensearch_upload: False

## Demo counters
- demo_query_count: 6
- successful_demo_query_count: 6
- total_demo_match_count: 42
- page_with_demo_match_count: 12
- field_count: 6
- source_bridge_record_count: 1497
- source_ranking_available_bridge_record_count: 1497

## Field counts
- covered_part_number: 150
- ipl_figure_item_or_quantity: 843
- ipl_part_number: 197
- ipl_text: 188
- manual_page_reference: 39
- page_rev_or_sequence_value: 80

## Safety/write counters
- unsafe_demo_record_count: 0
- answer_permission_count: 0
- can_answer_directly_count: 0
- can_prove_claims_count: 0
- source_truth_mutation_allowed_count: 0
- postgres_write_attempt_count: 0
- qdrant_write_attempt_count: 0
- opensearch_write_attempt_count: 0
- opensearch_upload_attempt_count: 0

## Demo queries
- query='120-36833-001' matches=1 pages=t_p_120_1176_p000003
  - analogy: Like looking up a product SKU in a store inventory index.
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-001 | boost=1.35
- query='25-21-00' matches=10 pages=t_p_120_1176_p000005
  - analogy: Like using a book index to jump to the right chapter/page.
  - t_p_120_1176_p000005 | manual_page_reference | 25-21-00 | boost=1.25
  - t_p_120_1176_p000005 | manual_page_reference | 25-21-00 | boost=1.25
  - t_p_120_1176_p000005 | manual_page_reference | 25-21-00 | boost=1.25
  - t_p_120_1176_p000005 | manual_page_reference | 25-21-00 | boost=1.25
  - t_p_120_1176_p000005 | manual_page_reference | 25-21-00 | boost=1.25
- query='607' matches=1 pages=t_p_120_1176_p000005
  - analogy: Like checking a table-of-contents line number or revision marker.
  - t_p_120_1176_p000005 | page_rev_or_sequence_value | 607 | boost=1.05
- query='MAINTENANCE MANUAL WITH' matches=10 pages=t_p_120_1176_p000027,t_p_120_1176_p000028,t_p_120_1176_p000029,t_p_120_1176_p000030,t_p_120_1176_p000031,t_p_120_1176_p000032,t_p_120_1176_p000033,t_p_120_1176_p000034,t_p_120_1176_p000036,t_p_120_1176_p000037
  - analogy: Like searching the notes column of a parts list.
  - t_p_120_1176_p000027 | ipl_text | MAINTENANCE MANUAL WITH | boost=1.0
  - t_p_120_1176_p000028 | ipl_text | MAINTENANCE MANUAL WITH | boost=1.0
  - t_p_120_1176_p000029 | ipl_text | MAINTENANCE MANUAL WITH | boost=1.0
  - t_p_120_1176_p000030 | ipl_text | MAINTENANCE MANUAL WITH | boost=1.0
  - t_p_120_1176_p000031 | ipl_text | MAINTENANCE MANUAL WITH | boost=1.0
- query='130' matches=10 pages=t_p_120_1176_p000027
  - analogy: Like searching by item number on an exploded-view diagram list.
  - t_p_120_1176_p000027 | ipl_figure_item_or_quantity | 130 | boost=0.95
  - t_p_120_1176_p000027 | ipl_figure_item_or_quantity | 130 | boost=0.95
  - t_p_120_1176_p000027 | ipl_figure_item_or_quantity | 130 | boost=0.95
  - t_p_120_1176_p000027 | ipl_figure_item_or_quantity | 130 | boost=0.95
  - t_p_120_1176_p000027 | ipl_figure_item_or_quantity | 130 | boost=0.95
- query='covered_part_number' matches=10 pages=t_p_120_1176_p000003
  - analogy: Like looking up a product SKU in a store inventory index.
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-001 | boost=1.35
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-003 | boost=1.35
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-005 | boost=1.35
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-501 | boost=1.35
  - t_p_120_1176_p000003 | covered_part_number | 120-36833-503 | boost=1.35

## Quality checks
- PASS source_readiness_quality_pass: observed=True expected=is True
- PASS source_bridge_quality_pass: observed=True expected=is True
- PASS readiness_status_ready_for_ranking_only: observed=READY_FOR_RETRIEVAL_RANKING_ONLY expected=READY_FOR_RETRIEVAL_RANKING_ONLY
- PASS demo_query_count: observed=6 expected=>= 3
- PASS successful_demo_query_count: observed=6 expected=>= 3
- PASS total_demo_match_count: observed=42 expected=>= 3
- PASS page_with_demo_match_count: observed=12 expected=>= 1
- PASS field_count: observed=6 expected=>= 4
- PASS unsafe_demo_record_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS can_answer_directly_count: observed=0 expected=== 0
- PASS can_prove_claims_count: observed=0 expected=== 0
- PASS postgres_write_attempt_count: observed=0 expected=== 0
- PASS qdrant_write_attempt_count: observed=0 expected=== 0
- PASS opensearch_write_attempt_count: observed=0 expected=== 0
- PASS opensearch_upload_attempt_count: observed=0 expected=== 0
