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
- e2e_query_input_record_count: 1
- routeable_query_count: 1
- planned_retrieval_query_count: 1
- unique_intent_count: 1
- schema_missing_required_key_record_count: 0

## Intent counts
- covered_part_number: 1

## Route counts
- normal_text: 1
- table: 1

## Retrieval channel counts
- graph_source_trace: 1
- qdrant_page_profiles: 1
- table_exact_search: 1
- table_hybrid_retrieval_bridge: 1

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

## Quality checks
- PASS e2e_query_input_record_count: observed=1 expected=>= 1
- PASS routeable_query_count: observed=1 expected=>= 1
- PASS planned_retrieval_query_count: observed=1 expected=>= 1
- PASS unique_intent_count: observed=1 expected=>= 1
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
