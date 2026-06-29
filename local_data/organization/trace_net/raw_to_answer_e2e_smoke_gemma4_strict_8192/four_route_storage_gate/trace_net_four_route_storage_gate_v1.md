# TRACE-Net Four Route Storage Gate v1

Quality status: **PASS**

## Summary

```json
{
  "answer_permission_count": 0,
  "blocked_records_csv_path": "local_data\\organization\\trace_net\\raw_to_answer_e2e_smoke_gemma4_strict_8192\\four_route_storage_gate\\trace_net_four_route_storage_gate_v1_blocked_records.csv",
  "can_answer_directly_count": 0,
  "can_prove_claims_count": 0,
  "final_do_not_embed_count": 59,
  "final_validated_route_counts": {
    "blank": 14,
    "image": 12,
    "plain_text": 163,
    "table": 320
  },
  "human_review_required_count": 0,
  "invalid_operational_route_count": 0,
  "manual_review_required_count": 0,
  "module": "trace_net_four_route_storage_gate_v1",
  "opensearch_candidates_jsonl_path": "local_data\\organization\\trace_net\\raw_to_answer_e2e_smoke_gemma4_strict_8192\\four_route_storage_gate\\trace_net_four_route_storage_gate_v1_opensearch_candidates.jsonl",
  "opensearch_index_allowed_count": 282,
  "opensearch_write_attempt_count": 0,
  "postgres_graph_manifest_jsonl_path": "local_data\\organization\\trace_net\\raw_to_answer_e2e_smoke_gemma4_strict_8192\\four_route_storage_gate\\trace_net_four_route_storage_gate_v1_postgres_graph_manifest.jsonl",
  "postgres_graph_record_count": 509,
  "postgres_write_attempt_count": 0,
  "qdrant_candidates_jsonl_path": "local_data\\organization\\trace_net\\raw_to_answer_e2e_smoke_gemma4_strict_8192\\four_route_storage_gate\\trace_net_four_route_storage_gate_v1_qdrant_candidates.jsonl",
  "qdrant_embedding_allowed_count": 450,
  "qdrant_write_attempt_count": 0,
  "raw_tiff_reference_preserved_count": 509,
  "ready_for_graph_ingestion_manifest": true,
  "ready_for_opensearch_candidate_export": true,
  "ready_for_qdrant_candidate_export": true,
  "ready_for_unresolved_escalation": true,
  "records_csv_path": "local_data\\organization\\trace_net\\raw_to_answer_e2e_smoke_gemma4_strict_8192\\four_route_storage_gate\\trace_net_four_route_storage_gate_v1_records.csv",
  "records_jsonl_path": "local_data\\organization\\trace_net\\raw_to_answer_e2e_smoke_gemma4_strict_8192\\four_route_storage_gate\\trace_net_four_route_storage_gate_v1_records.jsonl",
  "source_record_count": 509,
  "source_route_unresolved_retry_probe": "local_data\\organization\\trace_net\\raw_to_answer_e2e_smoke_gemma4_strict_8192\\route_unresolved_retry_probe\\trace_net_route_unresolved_retry_probe_v1.json",
  "source_route_unresolved_retry_probe_quality_status": "PASS",
  "source_truth_mutation_allowed_count": 0,
  "storage_decision_counts": {
    "graph_only_blank": 14,
    "graph_only_validator_gated": 45,
    "validated_graph_and_semantic_index": 168,
    "validated_graph_semantic_and_exact_index": 282
  },
  "storage_gate_record_count": 509,
  "unsafe_record_count": 0,
  "validator_gated_count": 45,
  "version": "v1"
}
```

## Storage contract

- Every page receives a Postgres graph/source-map record policy.
- Qdrant candidates are limited to validated, non-blank, non-blocked evidence.
- OpenSearch candidates are limited to validated table/exact-evidence records.
- Unresolved or blocked records remain source-traceable but are not embedded/indexed.
- This builder performs no writes to Postgres, Qdrant, or OpenSearch.
