# TRACE-Net Community-Aware Retrieval Simulation v1 import fix

This patch fixes the Step 22 public API names used by tests and wrapper scripts.

It adds compatibility entrypoints:

- `run_community_aware_retrieval_sim(...)`
- `quality_report(...)`

It also includes the flattened `groups` list in the returned report while keeping the existing `query_results` structure.

Safety behavior is unchanged:

- communities remain advisory only
- feedback remains advisory only
- neither can answer directly
- neither can prove claims
- neither can mutate source truth
