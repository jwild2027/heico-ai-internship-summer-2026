# TRACE-Net Feedback-Aware Search Simulation v1

This module simulates how validated TRACE-Net feedback policy signals would adjust the latest grouped search ranking.

It is simulation-only:

- does not mutate source truth
- does not mutate production search results
- does not mutate RAG eligibility
- ignores non-matching or review-only feedback signals

## Run

```bash
python scripts/simulate_trace_net_feedback_search.py --open
```

For an explicit query context:

```bash
python scripts/simulate_trace_net_feedback_search.py \
  --part-number 120-50645-009 \
  --open
```

## Quality

```bash
python scripts/check_trace_net_feedback_search_simulation_quality.py \
  --write-json \
  --min-groups 1 \
  --min-matching-feedback-signals 1 \
  --min-feedback-signals-used 1 \
  --max-unsafe-results 0 \
  --max-excluded-results 0 \
  --max-source-truth-mutations 0 \
  --max-context-warning-signals-used 0
```

## Outputs

```text
local_data/organization/trace_net/feedback_search_simulation/trace_net_feedback_search_simulation.json
local_data/organization/trace_net/feedback_search_simulation/trace_net_feedback_search_simulation_results.jsonl
local_data/organization/trace_net/feedback_search_simulation/trace_net_feedback_search_simulation_summary.json
local_data/organization/trace_net/feedback_search_simulation/trace_net_feedback_search_simulation_review.md
local_data/organization/trace_net/feedback_search_simulation/trace_net_feedback_search_simulation_review.html
local_data/organization/trace_net/feedback_search_simulation/trace_net_feedback_search_simulation_graph_nodes.json
local_data/organization/trace_net/feedback_search_simulation/trace_net_feedback_search_simulation_graph_edges.json
```
