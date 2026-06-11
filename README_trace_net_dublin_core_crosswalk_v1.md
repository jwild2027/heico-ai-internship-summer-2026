# TRACE-Net Dublin Core Page Metadata Crosswalk v1

This module exports a read-only Dublin Core + TRACE-Net metadata crosswalk for pages and documents.

## Purpose

Dublin Core gives standard catalog metadata:

- `dc:identifier`
- `dc:type`
- `dc:format`
- `dc:source`
- `dc:description`
- `dc:subject`
- `dc:relation`
- `dcterms:isPartOf`
- `dcterms:hasPart`
- `dcterms:provenance`
- `dcterms:extent`

TRACE-Net adds operational/evidence metadata:

- `trace_net:element_count`
- `trace_net:top_level_element_count`
- `trace_net:detailed_element_count`
- `trace_net:element_type_count`
- `trace_net:element_type_counts`
- `trace_net:review_required`
- `trace_net:complexity_class`
- `trace_net:citation_count`
- `trace_net:community_ids`
- `trace_net:part_numbers`
- `trace_net:source_trace_present`
- `trace_net:ocr_present`
- `trace_net:context_v2_present`

The crosswalk is metadata-only. It cannot answer directly, prove claims, mutate source truth, or promote evidence.

## Build

```bash
python scripts/build_trace_net_dublin_core_crosswalk_v1.py \
  --page-registry local_data/organization/trace_net/page_element_registry/trace_net_page_element_registry_v1.json \
  --table-cell-normalizer local_data/organization/trace_net/table_cell_normalizer/trace_net_table_cell_normalizer_v1.json \
  --figure-chart-understanding local_data/organization/trace_net/figure_chart_understanding/trace_net_figure_chart_understanding_v1.json \
  --visual-ink-layout-calibrator local_data/organization/trace_net/visual_ink_layout_calibrator/trace_net_visual_ink_layout_calibrator_v1.json \
  --element-graph-attachment local_data/organization/trace_net/element_graph_attachment/trace_net_element_graph_attachment_plan_v1.json \
  --leiden-communities local_data/organization/trace_net/leiden_graph_communities/trace_net_leiden_graph_communities_v1.json \
  --opensearch-adapter local_data/organization/trace_net/opensearch_adapter/trace_net_opensearch_adapter_v1.json \
  --feedback-memory local_data/organization/trace_net/feedback_memory/trace_net_feedback_memory_v1.json \
  --human-review-triage local_data/organization/trace_net/human_review_triage/trace_net_human_review_triage_v1.json \
  --output-dir local_data/organization/trace_net/dublin_core_crosswalk \
  --require-page-count 509 \
  --min-page-records 509 \
  --min-document-records 1 \
  --min-pages-with-element-counts 509 \
  --quality
```

## Quality

```bash
python scripts/check_trace_net_dublin_core_crosswalk_v1_quality.py \
  --report-path local_data/organization/trace_net/dublin_core_crosswalk/trace_net_dublin_core_crosswalk_v1.json \
  --require-page-count 509 \
  --min-page-records 509 \
  --min-document-records 1 \
  --min-pages-with-element-counts 509 \
  --write-json
```

## Outputs

- `trace_net_dublin_core_crosswalk_v1.json`
- `trace_net_dublin_core_pages_v1.jsonl`
- `trace_net_dublin_core_documents_v1.jsonl`
- `trace_net_dublin_core_crosswalk_v1_summary.json`
- `trace_net_dublin_core_crosswalk_v1_quality.json`
- `trace_net_dublin_core_crosswalk_field_map_v1.md`
- `trace_net_dublin_core_crosswalk_v1.md`
- `trace_net_dublin_core_crosswalk_v1.html`
