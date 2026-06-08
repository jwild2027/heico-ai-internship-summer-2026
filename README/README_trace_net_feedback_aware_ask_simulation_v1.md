# TRACE-Net Feedback-Aware Ask Simulation v1

Simulation-only layer that composes a feedback-aware answer draft from the current grouped search results and validated feedback search simulation output.

It does **not** mutate production search ranking, source truth, Evidence Consensus, RAG eligibility, trust tiers, or the normal answer draft.

## Flow

```text
trace_net_ask output
  -> feedback graph / validated policy signals
  -> feedback-aware search simulation
  -> feedback-aware ask simulation
  -> simulated answer comparison
```

## Inputs

```text
local_data/organization/trace_net/search/trace_net_search_grouped_results.jsonl
local_data/organization/trace_net/search/trace_net_search_grouped_summary.json
local_data/organization/trace_net/answers/trace_net_answer_draft.json
local_data/organization/trace_net/answers/trace_net_answer_summary.json
local_data/organization/trace_net/feedback_search_simulation/trace_net_feedback_search_simulation_results.jsonl
local_data/organization/trace_net/feedback_search_simulation/trace_net_feedback_search_simulation_summary.json
```

## Outputs

```text
local_data/organization/trace_net/feedback_ask_simulation/trace_net_feedback_ask_simulation.json
local_data/organization/trace_net/feedback_ask_simulation/trace_net_feedback_ask_simulation_summary.json
local_data/organization/trace_net/feedback_ask_simulation/trace_net_feedback_ask_simulation_answer.md
local_data/organization/trace_net/feedback_ask_simulation/trace_net_feedback_ask_simulation_answer.html
local_data/organization/trace_net/feedback_ask_simulation/trace_net_feedback_ask_simulation_evidence.jsonl
local_data/organization/trace_net/feedback_ask_simulation/trace_net_feedback_ask_simulation_graph_nodes.json
local_data/organization/trace_net/feedback_ask_simulation/trace_net_feedback_ask_simulation_graph_edges.json
```

## Run

```bash
python scripts/simulate_trace_net_feedback_ask.py --open
```

## Quality

```bash
python scripts/check_trace_net_feedback_ask_simulation_quality.py \
  --write-json \
  --min-pages 1 \
  --min-evidence-records 1 \
  --min-feedback-signals-used 1 \
  --min-groups-adjusted 1 \
  --min-rank-changed-records 1 \
  --max-unsafe-groups 0 \
  --max-excluded-groups 0 \
  --max-source-truth-mutations 0 \
  --max-context-warning-signals-used 0
```

Add `--require-answer-changed` when the simulation is expected to change order/ranks.

## Safety rules

```text
feedback is advisory only
context-warning signals are ignored
source truth is not mutated
unsafe/excluded groups fail quality
normal answer draft is not overwritten
```
