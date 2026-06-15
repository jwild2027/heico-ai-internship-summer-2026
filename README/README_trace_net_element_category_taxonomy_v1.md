# TRACE-Net Element Category Taxonomy v1

This step normalizes TRACE-Net page/graph/search/review element signals into a stable taxonomy for UI filtering, review triage, OpenSearch filters, and later category-aware Leiden/community overlays.

It is read-only. Categories cannot answer directly, prove claims, or mutate source truth.

## Inputs

Recommended inputs:

- refined Dublin Core crosswalk
- element graph attachment plan
- table cell normalizer
- figure/chart understanding
- callout visual part verifier
- human review triage
- OpenSearch adapter
- Leiden communities

## Outputs

Output folder:

```text
local_data/organization/trace_net/element_category_taxonomy/
```

Files:

```text
trace_net_element_category_taxonomy_v1.json
trace_net_element_category_records_v1.jsonl
trace_net_page_category_profiles_v1.jsonl
trace_net_element_category_taxonomy_v1_summary.json
trace_net_element_category_taxonomy_v1_quality.json
trace_net_element_category_taxonomy_v1_manifest.json
trace_net_element_category_taxonomy_v1.md
trace_net_element_category_taxonomy_v1.html
```

## Build

```bash
python scripts/build_trace_net_element_category_taxonomy_v1.py \
  --dublin-core-refined local_data/organization/trace_net/dublin_core_crosswalk_refined/trace_net_dublin_core_crosswalk_refinement_v1.json \
  --element-graph-attachment local_data/organization/trace_net/element_graph_attachment/trace_net_element_graph_attachment_plan_v1.json \
  --table-cell-normalizer local_data/organization/trace_net/table_cell_normalizer/trace_net_table_cell_normalizer_v1.json \
  --figure-chart-understanding local_data/organization/trace_net/figure_chart_understanding/trace_net_figure_chart_understanding_v1.json \
  --callout-visual-part-verifier local_data/organization/trace_net/callout_visual_part_verifier/trace_net_callout_visual_part_verifier_v1.json \
  --human-review-triage local_data/organization/trace_net/human_review_triage/trace_net_human_review_triage_v1.json \
  --opensearch-adapter local_data/organization/trace_net/opensearch_adapter/trace_net_opensearch_adapter_v1.json \
  --leiden-communities local_data/organization/trace_net/leiden_graph_communities/trace_net_leiden_graph_communities_v1.json \
  --output-dir local_data/organization/trace_net/element_category_taxonomy \
  --require-page-count 509 \
  --min-page-profiles 509 \
  --min-categorized-elements 1 \
  --min-diagram-categories 1 \
  --min-table-categories 1 \
  --min-part-categories 1 \
  --min-review-categories 1 \
  --quality
```

If the callout verifier artifact does not exist yet, omit `--callout-visual-part-verifier`.

## Quality

```bash
python scripts/check_trace_net_element_category_taxonomy_v1_quality.py \
  --report-path local_data/organization/trace_net/element_category_taxonomy/trace_net_element_category_taxonomy_v1.json \
  --require-page-count 509 \
  --min-page-profiles 509 \
  --min-categorized-elements 1 \
  --min-diagram-categories 1 \
  --min-table-categories 1 \
  --min-part-categories 1 \
  --min-review-categories 1 \
  --write-json
```

## Taxonomy shape

Each element category record has:

```text
element_family
element_category
element_role
supports_leiden_grouping
recommended_leiden_edge_policy
avoid_global_category_hub
```

Families include:

```text
source, text, table, visual, diagram, chart, part, citation, evidence,
trust, context, search, community, feedback, review, incident, operation,
page_trait, blank, other
```

## Leiden guidance

This module does not rerun Leiden. It prepares safe category metadata for a later Category-Aware Leiden Overlay.

Recommended future rule:

```text
Use page-local category nodes or low-weight edges.
Avoid one global category hub like category::table_cell connected to every table cell.
```
