# TRACE-Net Page Retrieval Large Eval v2

Status: `PAGE_RETRIEVAL_LARGE_EVAL_V2_BUILT`
Quality status: `PASS`

## Summary

- `query_record_count`: `200`
- `evaluated_record_count`: `200`
- `blank_expected_count`: `11`
- `context_v2_query_count`: `200`
- `graph_path_resolved_count`: `200`
- `llm_graph_path_card_count`: `200`
- `target_hit_at_1_count`: `150`
- `target_hit_at_10_count`: `195`
- `target_hit_at_k_count`: `198`
- `target_hit_at_k_rate`: `0.99`
- `answer_capable_payload_count`: `0`
- `claim_proof_payload_count`: `0`
- `source_truth_mutation_allowed_count`: `0`

## Safety contract

This artifact is read-only. It creates retrieval and LLM graph-path test cards only. It does not write to Postgres, Qdrant, OpenSearch, or source truth, and it does not grant answer permission.
