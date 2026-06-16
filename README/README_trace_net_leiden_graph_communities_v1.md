# TRACE-Net Leiden Graph Communities v1

Step 20 builds graph communities from the enriched TRACE-Net graph overlay.
It is read-only and does not write to Postgres, Qdrant, source files, trust records, or source truth.

## Purpose

After Step 19.2, the graph overlay has clean page, table, cell, visual, fishnet, evidence, citation, and part-candidate lineage. Step 20 groups those nodes into communities for:

- graph UI navigation
- retrieval boosting hints
- review prioritization
- part-family and table/visual neighborhood summaries
- future feedback-memory aggregation

Community membership is **not proof**. It is a routing and review helper only.

## Algorithm

The builder tries to use real Leiden community detection if these packages are installed:

```bash
python -m pip install python-igraph leidenalg
```

If those packages are not available, it falls back to deterministic connected components so local quality checks can still run.

TrustAuthority hub edges are excluded from the community graph to avoid collapsing unrelated evidence into one giant community through global authority nodes.

## Build

```bash
python scripts/build_trace_net_leiden_graph_communities_v1.py \
  --graph-overlay-part-normalizer local_data/organization/trace_net/graph_overlay_part_property_normalizer/trace_net_graph_overlay_part_property_normalizer_v1.json \
  --output-dir local_data/organization/trace_net/leiden_graph_communities \
  --algorithm auto \
  --resolution 1.0 \
  --require-page-count 509 \
  --min-communities 1 \
  --min-nodes 1000 \
  --min-edges 1000 \
  --min-page-nodes-with-community 509 \
  --min-part-candidate-nodes-with-community 301 \
  --min-table-cell-nodes-with-community 3090 \
  --min-nomenclature-edges-preserved 1 \
  --min-context-v2-edges-preserved 50 \
  --min-confirmed-blank-preserve-source-trace 14 \
  --require-source-overlay-quality-pass \
  --quality
```

## Check quality

```bash
python scripts/check_trace_net_leiden_graph_communities_v1_quality.py \
  --report-path local_data/organization/trace_net/leiden_graph_communities/trace_net_leiden_graph_communities_v1.json \
  --require-page-count 509 \
  --min-communities 1 \
  --min-nodes 1000 \
  --min-edges 1000 \
  --min-page-nodes-with-community 509 \
  --min-part-candidate-nodes-with-community 301 \
  --min-table-cell-nodes-with-community 3090 \
  --min-nomenclature-edges-preserved 1 \
  --min-context-v2-edges-preserved 50 \
  --min-confirmed-blank-preserve-source-trace 14 \
  --require-source-overlay-quality-pass \
  --write-json
```

## Safety contract

- `can_answer_directly = false`
- `can_prove_claims = false`
- `can_mutate_source_truth = false`
- communities require source/citation/authority checks before any answer use
- feedback and ranking may use communities only as advisory routing signals

## Outputs

```text
local_data/organization/trace_net/leiden_graph_communities/
  trace_net_leiden_graph_communities_v1.json
  trace_net_leiden_graph_communities_v1_communities.jsonl
  trace_net_leiden_graph_communities_v1_node_membership.jsonl
  trace_net_leiden_graph_communities_v1_edges.jsonl
  trace_net_leiden_graph_communities_v1_summary.json
  trace_net_leiden_graph_communities_v1_manifest.json
  trace_net_leiden_graph_communities_v1_quality.json
  trace_net_leiden_graph_communities_v1.md
  trace_net_leiden_graph_communities_v1.html
```
