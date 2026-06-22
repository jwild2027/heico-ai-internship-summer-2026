# TRACE-Net E2E Query Input v1 Inspect

Quality status: **PASS**

## Purpose
This artifact turns user questions into safe query-plan records for the later E2E retrieval runtime.
It does not retrieve, answer, mutate source truth, or write to runtime services.

## Query input contract
- purpose: Convert user questions into safe query-plan artifacts for the later E2E retrieval runtime.
- retrieval_permission: ranking_only_until_final_gate
- answer_authority: blocked
- can_answer_directly: False
- can_prove_claims: False
- source_truth_mutation_allowed: False
- writes_to_postgres: False
- writes_to_qdrant: False
- writes_to_opensearch: False
- uploads_to_opensearch: False

## Main counters
- e2e_query_input_record_count: 5
- routeable_query_count: 5
- planned_retrieval_query_count: 5
- unique_intent_count: 4
- schema_missing_required_key_record_count: 0

## Intent counts
- covered_part_number: 2
- ipl_figure_item_or_quantity: 1
- manual_page_reference: 1
- table_text: 1

## Route counts
- image_visual: 1
- normal_text: 4
- table: 5

## Retrieval channel counts
- graph_source_trace: 4
- qdrant_page_profiles: 4
- table_exact_search: 5
- table_hybrid_retrieval_bridge: 5

## Safety/write counters
- unsafe_query_input_record_count: 0
- answer_permission_count: 0
- can_answer_directly_count: 0
- can_prove_claims_count: 0
- source_truth_mutation_allowed_count: 0
- postgres_write_attempt_count: 0
- qdrant_write_attempt_count: 0
- opensearch_write_attempt_count: 0
- opensearch_upload_attempt_count: 0

## Query records
- e2e_query_v1_0001 | covered_part_number | Find part number 120-36833-001
  - routes: table, normal_text
  - channels: table_exact_search, table_hybrid_retrieval_bridge, qdrant_page_profiles, graph_source_trace
  - terms: 120-36833-001 (part_number)
- e2e_query_v1_0002 | manual_page_reference | Where is manual reference 25-21-00 used?
  - routes: table, normal_text
  - channels: table_exact_search, table_hybrid_retrieval_bridge, qdrant_page_profiles, graph_source_trace
  - terms: 25-21-00 (manual_page_reference)
- e2e_query_v1_0003 | ipl_figure_item_or_quantity | Find IPL item 130
  - routes: table, image_visual
  - channels: table_exact_search, table_hybrid_retrieval_bridge, graph_source_trace
  - terms: 130 (numeric_token)
- e2e_query_v1_0004 | table_text | Search table text MAINTENANCE MANUAL WITH
  - routes: table, normal_text
  - channels: table_exact_search, table_hybrid_retrieval_bridge, qdrant_page_profiles
  - terms: MAINTENANCE MANUAL WITH (table_text_phrase)
- e2e_query_v1_0005 | covered_part_number | What maintenance manual pages mention covered part numbers?
  - routes: table, normal_text
  - channels: table_exact_search, table_hybrid_retrieval_bridge, qdrant_page_profiles, graph_source_trace
  - terms: What maintenance manual pages mention covered part numbers? (free_text)

## Quality checks
- PASS e2e_query_input_record_count: observed=5 expected=>= 5
- PASS routeable_query_count: observed=5 expected=>= 5
- PASS planned_retrieval_query_count: observed=5 expected=>= 5
- PASS unique_intent_count: observed=4 expected=>= 4
- PASS schema_missing_required_key_record_count: observed=0 expected=== 0
- PASS unsafe_query_input_record_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS can_answer_directly_count: observed=0 expected=== 0
- PASS can_prove_claims_count: observed=0 expected=== 0
- PASS postgres_write_attempt_count: observed=0 expected=== 0
- PASS qdrant_write_attempt_count: observed=0 expected=== 0
- PASS opensearch_write_attempt_count: observed=0 expected=== 0
- PASS opensearch_upload_attempt_count: observed=0 expected=== 0
- PASS all_records_retrieval_only: observed=True expected=is True
