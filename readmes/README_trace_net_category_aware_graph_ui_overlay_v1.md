# TRACE-Net Category-Aware Graph UI Overlay v1

Read-only UI overlay that connects the existing graph UI community overlay with the category-aware Leiden overlay.

It adds UI-ready nodes/cards for:

- category-aware community cards
- page category profile cards
- category-aware community-to-page-profile edges
- copied page-local category hint nodes/edges from the category-aware Leiden overlay

Safety contract:

- categories are navigation/retrieval/review metadata only
- communities are not proof
- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no direct-answer or claim-proof permission

## Build

```bash
python scripts/build_trace_net_category_aware_graph_ui_overlay_v1.py \
  --graph-ui-community-overlay local_data/organization/trace_net/graph_ui_community_overlay/trace_net_graph_ui_community_overlay_v1.json \
  --category-aware-leiden-overlay local_data/organization/trace_net/category_aware_leiden_overlay/trace_net_category_aware_leiden_overlay_v1.json \
  --element-category-taxonomy local_data/organization/trace_net/element_category_taxonomy/trace_net_element_category_taxonomy_v1.json \
  --dublin-core-refined local_data/organization/trace_net/dublin_core_crosswalk_refined/trace_net_dublin_core_crosswalk_refinement_v1.json \
  --output-dir local_data/organization/trace_net/category_aware_graph_ui_overlay \
  --require-page-count 509 \
  --min-communities 229 \
  --min-category-aware-community-cards 1 \
  --min-page-category-profile-cards 509 \
  --min-category-ui-edges 1 \
  --require-source-graph-ui-quality-pass \
  --require-source-category-overlay-quality-pass \
  --quality
```

## Check quality

```bash
python scripts/check_trace_net_category_aware_graph_ui_overlay_v1_quality.py \
  --report-path local_data/organization/trace_net/category_aware_graph_ui_overlay/trace_net_category_aware_graph_ui_overlay_v1.json \
  --require-page-count 509 \
  --min-communities 229 \
  --min-category-aware-community-cards 1 \
  --min-page-category-profile-cards 509 \
  --min-category-ui-edges 1 \
  --require-source-graph-ui-quality-pass \
  --require-source-category-overlay-quality-pass \
  --write-json
```

## Outputs

- `trace_net_category_aware_graph_ui_overlay_v1.json`
- `trace_net_category_aware_graph_ui_overlay_v1_nodes.jsonl`
- `trace_net_category_aware_graph_ui_overlay_v1_edges.jsonl`
- `trace_net_category_aware_graph_ui_overlay_v1_community_cards.jsonl`
- `trace_net_category_aware_graph_ui_overlay_v1_page_cards.jsonl`
- `trace_net_category_aware_graph_ui_overlay_v1_summary.json`
- `trace_net_category_aware_graph_ui_overlay_v1_quality.json`
- `trace_net_category_aware_graph_ui_overlay_v1.md`
- `trace_net_category_aware_graph_ui_overlay_v1.html`
