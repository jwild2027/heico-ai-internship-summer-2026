# TRACE-Net Weighted Search Simulation v1

Simulation-only module that applies the official `trace_net_weights_policy_v1` to the latest grouped search results.

It reads:

```text
local_data/organization/trace_net/search/trace_net_search_grouped_results.jsonl
local_data/organization/trace_net/search/trace_net_search_grouped_summary.json
local_data/organization/trace_net/search/trace_net_search_summary.json
local_data/organization/trace_net/weights/trace_net_weights_policy.json
local_data/organization/trace_net/feedback/feedback_policy_signals.jsonl
```

It writes:

```text
local_data/organization/trace_net/weighted_search/trace_net_weighted_search_simulation.json
local_data/organization/trace_net/weighted_search/trace_net_weighted_search_simulation_results.jsonl
local_data/organization/trace_net/weighted_search/trace_net_weighted_search_simulation_summary.json
local_data/organization/trace_net/weighted_search/trace_net_weighted_search_simulation_review.md
local_data/organization/trace_net/weighted_search/trace_net_weighted_search_simulation_review.html
local_data/organization/trace_net/weighted_search/trace_net_weighted_search_simulation_graph_nodes.json
local_data/organization/trace_net/weighted_search/trace_net_weighted_search_simulation_graph_edges.json
```

## Safety

This does **not** mutate production ranking, source truth, Evidence Consensus, RAG eligibility, trust tiers, or feedback. It is a sidecar comparison report.

It enforces that:

```text
unsafe weighted results = 0
excluded weighted results = 0
source truth mutations = 0
context-warning feedback used = 0
```

## Run

```bash
python scripts/simulate_trace_net_weighted_search.py \
  --part-number 120-50645-009 \
  --open
```

Or use latest search context:

```bash
python scripts/simulate_trace_net_weighted_search.py --open
```

## Quality

```bash
python scripts/check_trace_net_weighted_search_quality.py \
  --write-json \
  --min-groups 1 \
  --min-pages 1 \
  --min-rank-comparison-records 1 \
  --max-unsafe-results 0 \
  --max-excluded-results 0 \
  --max-source-truth-mutations 0 \
  --max-context-warning-signals-used 0
```

For feedback-sensitive tests:

```bash
python scripts/check_trace_net_weighted_search_quality.py \
  --write-json \
  --min-groups 1 \
  --min-pages 1 \
  --min-rank-comparison-records 1 \
  --min-feedback-signals-used 1 \
  --min-groups-adjusted 1 \
  --max-unsafe-results 0 \
  --max-excluded-results 0 \
  --max-source-truth-mutations 0 \
  --max-context-warning-signals-used 0
```

If the current query has enough feedback to reorder pages, add:

```bash
--min-rank-changed-records 1
```

## Formula

Weighted page score is computed as:

```text
base score
+ bucket bonuses from trace_net_weights_policy.json
+ evidence diversity bonus
+ exact/term match bonuses
+ confidence bonus
+ validated feedback adjustment
```

Validated feedback is capped using the official feedback cap in the weights policy.
Context-warning feedback is ignored.
