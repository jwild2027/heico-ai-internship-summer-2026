# TRACE-Net Community-Aware Retrieval Simulation v1 API fix

This patch fixes the public Step 22 API mismatch from the first patch.

It adds the expected module-level entrypoints:

- `run_community_aware_retrieval_sim(...)`
- `quality_report(...)`

It also ensures the returned report includes a flattened `groups` list in addition to `query_results`.

Argument compatibility added:

- `max_groups_per_query` maps to `max_groups`
- `min_feedback_boosted_results` maps to `min_feedback_adjusted_results`
- `write_json_flag` maps to `write_json_report`

Safety behavior is unchanged:

- Leiden communities are advisory only
- feedback memory is advisory only
- neither can answer directly
- neither can prove claims
- neither can mutate source truth
