# TRACE-Net Community Ablation Evaluation

This patch adds a measurement layer for deciding when Leiden/community detection is useful and when simpler grouping is enough.

It compares:

- `no_community`: each page is its own group
- `route_grouping`: deterministic TRACE-Net route/trust/role grouping
- `networkx_greedy_modularity`: fallback community detection
- `leiden`: real Leiden, when `igraph` + `leidenalg` are installed

It does not mutate the source graph.

## Run tests

```bash
python -m pytest \
  tests/unit/test_tiff_trace_net_community_ablation.py \
  tests/unit/test_tiff_trace_net_community_ablation_quality.py \
  -q
```

## Run the ablation

```bash
python scripts/evaluate_trace_net_communities.py \
  --algorithms all \
  --min-pages 509
```

## Quality gate

```bash
python scripts/check_trace_net_community_ablation_quality.py \
  --write-json \
  --min-pages 509 \
  --min-algorithms 3
```

Require real Leiden:

```bash
python scripts/check_trace_net_community_ablation_quality.py \
  --write-json \
  --min-pages 509 \
  --min-algorithms 4 \
  --require-leiden
```

## Outputs

```text
local_data/organization/communities/community_ablation_eval.json
local_data/organization/communities/community_ablation_eval.md
local_data/organization/communities/community_ablation_quality.json
```

## How to interpret

Use the scores as a decision layer:

- If `route_grouping` beats Leiden for repair batching, use route grouping for repair work.
- If Leiden beats route grouping for retrieval expansion or neighborhood discovery, use Leiden for exploration/community summaries.
- Never use communities as the source of truth. Core source traceability should still use deterministic graph traversal.

## Metrics

The evaluator reports:

- community count
- largest community size/ratio
- singleton count
- size entropy/gini
- route purity
- table-route purity
- page-role purity
- image-class purity
- trust-tier purity
- table/hallucination/review trait concentration
- repair batching score
- retrieval expansion score
- Leiden-vs-route deltas
