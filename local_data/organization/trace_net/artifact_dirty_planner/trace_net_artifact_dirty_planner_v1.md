# TRACE-Net Artifact Dirty Planner v1

Quality status: `PASS`
Status: `DIRTY_PLAN_BUILT`

## Summary

- `source_registry_quality_status`: `PASS`
- `seed_artifact_count`: `2`
- `dirty_artifact_count`: `8`
- `planner_record_count`: `8`
- `dependency_edge_count`: `179`
- `dependency_cycle_count`: `0`
- `default_rule_edge_count`: `37`
- `source_truth_mutation_allowed_count`: `0`

## Dirty artifacts

- 1. `ask_api_dynamic_retrieval_v2` depth=1 seeds=['opensearch_adapter', 'opensearch_loader_smoke']
- 2. `hybrid_retrieval_v2` depth=1 seeds=['opensearch_adapter', 'opensearch_loader_smoke']
- 3. `opensearch_loader_smoke` depth=1 seeds=['opensearch_adapter']
- 4. `ask_api_final_return_policy_v21` depth=2 seeds=['opensearch_adapter', 'opensearch_loader_smoke']
- 5. `dynamic_final_gate_execution` depth=2 seeds=['opensearch_adapter', 'opensearch_loader_smoke']
- 6. `retrieval_critic` depth=2 seeds=['opensearch_adapter', 'opensearch_loader_smoke']
- 7. `answer_claim_critic` depth=3 seeds=['opensearch_adapter', 'opensearch_loader_smoke']
- 8. `evidence_sufficiency_critic` depth=3 seeds=['opensearch_adapter', 'opensearch_loader_smoke']
