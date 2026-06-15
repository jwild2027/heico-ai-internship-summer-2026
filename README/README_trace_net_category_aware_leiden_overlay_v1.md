# TRACE-Net Category-Aware Leiden Overlay v1

Read-only overlay that combines existing Leiden communities with the cleaned TRACE-Net Element Category Taxonomy page profiles.

## Purpose

This module improves community labels and graph/UI/review grouping hints without creating giant global category hubs.

It produces:

- category-aware community profiles
- page category membership rows
- page-local category hint nodes
- low-weight category overlay edges
- page-to-page category similarity edges
- quality and HTML/Markdown reports

## Safety contract

- Category metadata is navigation/retrieval/review-only.
- Categories cannot answer directly.
- Categories cannot prove claims.
- Categories cannot mutate source truth.
- This module does not write Postgres, Qdrant, OpenSearch, source files, or graph truth.

## Run

```bash
python scripts/build_trace_net_category_aware_leiden_overlay_v1.py \
  --leiden-communities local_data/organization/trace_net/leiden_graph_communities/trace_net_leiden_graph_communities_v1.json \
  --element-category-taxonomy local_data/organization/trace_net/element_category_taxonomy/trace_net_element_category_taxonomy_v1.json \
  --dublin-core-refined local_data/organization/trace_net/dublin_core_crosswalk_refined/trace_net_dublin_core_crosswalk_refinement_v1.json \
  --graph-ui-community-overlay local_data/organization/trace_net/graph_ui_community_overlay/trace_net_graph_ui_community_overlay_v1.json \
  --output-dir local_data/organization/trace_net/category_aware_leiden_overlay \
  --require-page-count 509 \
  --min-communities 229 \
  --min-page-category-profiles 509 \
  --min-communities-with-category-summary 1 \
  --min-category-overlay-edges 1 \
  --require-source-leiden-quality-pass \
  --require-source-taxonomy-quality-pass \
  --quality
```

## Check quality

```bash
python scripts/check_trace_net_category_aware_leiden_overlay_v1_quality.py \
  --report-path local_data/organization/trace_net/category_aware_leiden_overlay/trace_net_category_aware_leiden_overlay_v1.json \
  --require-page-count 509 \
  --min-communities 229 \
  --min-page-category-profiles 509 \
  --min-communities-with-category-summary 1 \
  --min-category-overlay-edges 1 \
  --require-source-leiden-quality-pass \
  --require-source-taxonomy-quality-pass \
  --write-json
```

## Outputs

- `trace_net_category_aware_leiden_overlay_v1.json`
- `trace_net_category_aware_leiden_overlay_v1_communities.jsonl`
- `trace_net_category_aware_leiden_overlay_v1_page_membership.jsonl`
- `trace_net_category_aware_leiden_overlay_v1_nodes.jsonl`
- `trace_net_category_aware_leiden_overlay_v1_edges.jsonl`
- `trace_net_category_aware_leiden_overlay_v1_summary.json`
- `trace_net_category_aware_leiden_overlay_v1_quality.json`
- `trace_net_category_aware_leiden_overlay_v1.md`
- `trace_net_category_aware_leiden_overlay_v1.html`

## Notes

The overlay intentionally uses page-local category hint nodes like:

```text
page_category::<page_id>::<family>
```

It does not create global hubs like:

```text
category::table_cell
```

This prevents category-aware community organization from pulling unrelated pages together through high-degree category hub nodes.
