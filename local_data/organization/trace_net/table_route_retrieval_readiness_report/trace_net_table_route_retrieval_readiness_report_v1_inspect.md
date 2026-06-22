# TRACE-Net Table Route Retrieval Readiness Report v1 Inspect

Quality status: **PASS**

## Readiness status
- retrieval_readiness_status: READY_FOR_RETRIEVAL_RANKING_ONLY
- retrieval_permission: ranking_only
- answer_authority: blocked
- ready_for_hybrid_retrieval_ranking: True
- ready_for_live_opensearch_upload: False

## Main counters
- exact_search_document_count: 1497
- successful_smoke_query_count: 6
- total_smoke_match_count: 42
- bridge_record_count: 1497
- ranking_available_bridge_record_count: 1497
- page_with_ranking_signal_count: 13
- field_count: 6
- schema_missing_required_key_record_count: 0

## Field counts
- covered_part_number: 150
- ipl_figure_item_or_quantity: 843
- ipl_part_number: 197
- ipl_text: 188
- manual_page_reference: 39
- page_rev_or_sequence_value: 80

## Safety/write counters
- unsafe_total_count: 0
- answer_permission_count: 0
- can_answer_directly_count: 0
- can_prove_claims_count: 0
- source_truth_mutation_allowed_count: 0
- postgres_write_attempt_count: 0
- qdrant_write_attempt_count: 0
- opensearch_write_attempt_count: 0
- opensearch_upload_attempt_count: 0

## Quality checks
- PASS source_exact_search_adapter_quality_pass: observed=True expected=is True
- PASS source_exact_search_smoke_quality_pass: observed=True expected=is True
- PASS source_bridge_quality_pass: observed=True expected=is True
- PASS source_integration_audit_quality_pass: observed=True expected=is True
- PASS exact_search_document_count: observed=1497 expected=>= 1000
- PASS successful_smoke_query_count: observed=6 expected=>= 3
- PASS total_smoke_match_count: observed=42 expected=>= 3
- PASS bridge_record_count: observed=1497 expected=>= 1000
- PASS ranking_available_bridge_record_count: observed=1497 expected=>= 1000
- PASS page_with_ranking_signal_count: observed=13 expected=>= 1
- PASS field_count: observed=6 expected=>= 4
- PASS schema_missing_required_key_record_count: observed=0 expected=== 0
- PASS unsafe_total_count: observed=0 expected=<= 0
- PASS answer_permission_count: observed=0 expected=<= 0
- PASS source_truth_mutation_allowed_count: observed=0 expected=<= 0
- PASS can_answer_directly_count: observed=0 expected=== 0
- PASS can_prove_claims_count: observed=0 expected=== 0
- PASS postgres_write_attempt_count: observed=0 expected=== 0
- PASS qdrant_write_attempt_count: observed=0 expected=== 0
- PASS opensearch_write_attempt_count: observed=0 expected=== 0
- PASS opensearch_upload_attempt_count: observed=0 expected=== 0
