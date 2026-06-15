# TRACE-Net Community-Aware Retrieval Simulation v1

Step 22 combines three advisory retrieval signals:

1. Hybrid retrieval groups from Step 7.
2. Leiden graph communities from Step 20.
3. Sanitized feedback memory from Step 21.

It produces a read-only ranking simulation under:

```text
local_data/organization/trace_net/community_aware_retrieval_sim/
```

## Safety contract

Community and feedback signals are advisory only.

They can:

```text
boost/demote retrieval groups
help review routing
help graph UI/community navigation
help future feedback-aware retrieval simulation
```

They cannot:

```text
answer directly
prove claims
mutate source truth
override citations
override trust authority
override the final answer gate
```

## Build

```bash
python scripts/run_trace_net_community_aware_retrieval_sim_v1.py \
  --hybrid-report local_data/organization/trace_net/hybrid_retrieval_sim/trace_net_hybrid_retrieval_sim_v1.json \
  --leiden-communities local_data/organization/trace_net/leiden_graph_communities/trace_net_leiden_graph_communities_v1.json \
  --feedback-memory local_data/organization/trace_net/feedback_memory/trace_net_feedback_memory_v1.json \
  --output-dir local_data/organization/trace_net/community_aware_retrieval_sim \
  --max-groups 8 \
  --min-queries 5 \
  --min-queries-with-results 5 \
  --min-grouped-results 25 \
  --min-community-boosted-results 25 \
  --min-feedback-memory-records 1 \
  --quality
```

If you want to require feedback to actually adjust at least one ranked result, add:

```bash
--min-feedback-adjusted-results 1
```

That may depend on whether your feedback target matches one of the current hybrid result pages, citations, or communities.

## Quality check

```bash
python scripts/check_trace_net_community_aware_retrieval_sim_v1_quality.py \
  --report-path local_data/organization/trace_net/community_aware_retrieval_sim/trace_net_community_aware_retrieval_sim_v1.json \
  --min-queries 5 \
  --min-queries-with-results 5 \
  --min-grouped-results 25 \
  --min-community-boosted-results 25 \
  --min-feedback-memory-records 1 \
  --write-json
```

## Output files

```text
trace_net_community_aware_retrieval_sim_v1.json
trace_net_community_aware_retrieval_sim_v1_results.jsonl
trace_net_community_aware_retrieval_sim_v1_groups.jsonl
trace_net_community_aware_retrieval_sim_v1_summary.json
trace_net_community_aware_retrieval_sim_v1_manifest.json
trace_net_community_aware_retrieval_sim_v1_quality.json
trace_net_community_aware_retrieval_sim_v1.md
trace_net_community_aware_retrieval_sim_v1.html
```

## Interpretation

A group score is adjusted as:

```text
community_aware_score = base_hybrid_score + community_boost + feedback_advisory_delta
```

The score is still retrieval-only. It does not authorize answers.

Answer use still requires:

```text
source resolution
citation
trust authority
final answer gate
```
