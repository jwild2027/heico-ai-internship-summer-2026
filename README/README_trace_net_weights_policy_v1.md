# TRACE-Net Weights Policy v1

This patch stores the first official TRACE-Net weight recommendations as a versioned, quality-gated config artifact.

It does **not** change production ranking, source truth, Evidence Consensus, RAG eligibility, or feedback behavior by itself.

## Build

```bash
python scripts/build_trace_net_weights_policy.py --open
```

Writes:

```text
local_data/organization/trace_net/weights/trace_net_weights_policy.json
local_data/organization/trace_net/weights/trace_net_weights_policy_summary.json
local_data/organization/trace_net/weights/trace_net_weights_policy_report.md
local_data/organization/trace_net/weights/trace_net_weights_policy_report.html
local_data/organization/trace_net/weights/trace_net_weights_policy_graph_nodes.json
local_data/organization/trace_net/weights/trace_net_weights_policy_graph_edges.json
```

## Quality

```bash
python scripts/check_trace_net_weights_policy_quality.py \
  --write-json \
  --min-layers 7 \
  --max-validation-errors 0
```

## Included policy areas

- layer-specific evidence confidence weights
- layer-specific thresholds and max tiers
- risk scores with max-risk combination
- retrieval ranking bonuses
- validated feedback adjustment weights
- global safety gates

## Safety

The policy is advisory/config-only. Downstream modules must explicitly opt in.

Global gates include:

- source-untraceable records must not enter RAG
- metadata/prompt/refusal leaks must not enter RAG
- D-tier records must not enter RAG
- routing-only layers must not enter RAG directly
- feedback must not mutate source truth
- context-warning feedback must not adjust ranking
