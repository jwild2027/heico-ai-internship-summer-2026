# TRACE-Net Graph UI Community Overlay v1

Step 23 builds a read-only graph UI overlay that links Leiden graph communities, sanitized feedback memory, and community-aware retrieval results onto the enriched TRACE-Net graph overlay.

It does not write to Postgres or Qdrant and does not mutate source truth.

## Safety rule

Communities and feedback are advisory only:

- They can guide UI navigation, retrieval ranking, and review.
- They cannot answer directly.
- They cannot prove claims.
- They cannot mutate source truth.
- They cannot override citations, trust authority, or the final answer gate.

## Build

```bash
python scripts/build_trace_net_graph_ui_community_overlay_v1.py \
  --graph-overlay-part-normalizer local_data/organization/trace_net/graph_overlay_part_property_normalizer/trace_net_graph_overlay_part_property_normalizer_v1.json \
  --leiden-communities local_data/organization/trace_net/leiden_graph_communities/trace_net_leiden_graph_communities_v1.json \
  --feedback-memory local_data/organization/trace_net/feedback_memory/trace_net_feedback_memory_v1.json \
  --community-aware-retrieval local_data/organization/trace_net/community_aware_retrieval_sim/trace_net_community_aware_retrieval_sim_v1.json \
  --output-dir local_data/organization/trace_net/graph_ui_community_overlay \
  --require-page-count 509 \
  --min-overlay-nodes 1000 \
  --min-overlay-edges 1000 \
  --min-communities 229 \
  --min-page-nodes-with-community 509 \
  --min-part-candidate-nodes-with-community 301 \
  --min-table-cell-nodes-with-community 3090 \
  --min-feedback-memory-records-linked 1 \
  --min-community-aware-results-linked 1 \
  --min-nomenclature-edges-preserved 1 \
  --min-context-v2-edges-preserved 50 \
  --min-confirmed-blank-preserve-source-trace 14 \
  --require-source-overlay-quality-pass \
  --require-leiden-quality-pass \
  --require-feedback-quality-pass \
  --require-community-aware-quality-pass \
  --quality
```

## Quality

```bash
python scripts/check_trace_net_graph_ui_community_overlay_v1_quality.py \
  --report-path local_data/organization/trace_net/graph_ui_community_overlay/trace_net_graph_ui_community_overlay_v1.json \
  --require-page-count 509 \
  --min-overlay-nodes 1000 \
  --min-overlay-edges 1000 \
  --min-communities 229 \
  --min-page-nodes-with-community 509 \
  --min-part-candidate-nodes-with-community 301 \
  --min-table-cell-nodes-with-community 3090 \
  --min-feedback-memory-records-linked 1 \
  --min-community-aware-results-linked 1 \
  --min-nomenclature-edges-preserved 1 \
  --min-context-v2-edges-preserved 50 \
  --min-confirmed-blank-preserve-source-trace 14 \
  --require-source-overlay-quality-pass \
  --require-leiden-quality-pass \
  --require-feedback-quality-pass \
  --require-community-aware-quality-pass \
  --write-json
```
