# TRACE-Net Page Query Response Dataset v1

Status: `PAGE_QUERY_RESPONSE_DATASET_BUILT`
Quality status: `PASS`

## Summary

- record_count: `200`
- response_count: `200`
- blank_record_count: `11`
- blank_response_count: `11`
- graph_path_resolved_count: `200`
- source_identity_resolved_count: `200`
- qdrant_evaluated_record_count: `200`
- qdrant_target_hit_at_k_count: `198`
- qdrant_target_hit_at_k_rate: `0.99`
- unsafe_response_count: `0`
- can_answer_directly_count: `0`
- can_prove_claims_count: `0`
- source_truth_mutation_allowed_count: `0`

## Safety contract

This artifact is a read-only viewing dataset. It does not grant answer permission, claim-proof authority, or source-truth mutation permission.

## Outputs

- Records JSONL: `local_data\organization\trace_net\page_query_response_dataset\trace_net_page_query_response_dataset_v1_records.jsonl`
- Responses JSONL: `local_data\organization\trace_net\page_query_response_dataset\trace_net_page_query_response_dataset_v1_responses.jsonl`
