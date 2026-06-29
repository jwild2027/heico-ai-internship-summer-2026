# TRACE-Net Route Unresolved Retry/Probe v1

This artifact retries only validator-gated unresolved pages using conservative automatic probes.
It does not grant answer permission or mutate source truth.

## Summary

- **answer_permission_count**: `0`
- **can_answer_directly_count**: `0`
- **can_prove_claims_count**: `0`
- **final_do_not_embed_count**: `59`
- **final_validated_route_count**: `464`
- **final_validated_route_counts**: `{'plain_text': 158, 'blank': 14, 'table': 282, 'image': 10}`
- **human_review_replaced_by_retry_probe**: `True`
- **human_review_required_count**: `0`
- **manual_review_required_count**: `0`
- **module**: `trace_net_route_unresolved_retry_probe_v1`
- **opensearch_index_allowed_count**: `282`
- **opensearch_write_attempt_count**: `0`
- **postgres_write_attempt_count**: `0`
- **qdrant_embedding_allowed_count**: `450`
- **qdrant_write_attempt_count**: `0`
- **ready_for_unresolved_retry_escalation**: `True`
- **ready_for_validated_storage**: `True`
- **remaining_validator_gated_unresolved_count**: `45`
- **retry_attempted_count**: `150`
- **retry_decision_counts**: `{'already_validated': 359, 'retry_validated_primary_or_candidate_route': 105, 'validator_gated_unresolved_after_retry': 45}`
- **retry_probe_record_count**: `509`
- **retry_status_counts**: `{'not_needed_already_validated': 359, 'retry_validated': 105, 'retry_unresolved_validator_gated': 45}`
- **retry_validated_count**: `105`
- **source_record_count**: `509`
- **source_route_validator_runner_quality_status**: `PASS`
- **source_truth_mutation_allowed_count**: `0`
- **unsafe_record_count**: `0`
- **version**: `v1`

## Safety contract

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
