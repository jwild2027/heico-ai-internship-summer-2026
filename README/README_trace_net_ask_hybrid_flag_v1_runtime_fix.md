# TRACE-Net Ask Hybrid Flag v1 Runtime Fix

This patch fixes the Step 9 ask hybrid wrapper so it calls the Step 7 hybrid
retrieval simulator with the current Step 7 keyword names.

The previous wrapper passed prototype arguments such as `database_url`,
`max_groups_per_query`, `min_ranked_groups`, and `min_unique_group_pages`.
The current `run_hybrid_retrieval_sim()` implementation does not accept those
names, so the ask flag failed before it could write its report.

The fix:

- maps `max_groups` to the Step 7 `max_groups` argument;
- uses `min_grouped_results`, `min_resolved_candidate_hits`, and
  `min_resolved_page_profile_hits`;
- filters kwargs through the installed Step 7 simulator signature before
  calling it;
- keeps `database_url` accepted by the ask CLI for future compatibility, but it
  is not passed to Step 7 because Step 7 does not use Postgres directly.

The safety contract is unchanged: hybrid ask mode remains simulation-only and
cannot compose an answer, prove claims, mutate source truth, or bypass source /
citation / trust authority gates.
