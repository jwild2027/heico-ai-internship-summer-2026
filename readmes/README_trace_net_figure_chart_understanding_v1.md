# TRACE-Net Figure / Chart / Diagram Understanding v1

Step 16 is a read-only front-start TRACE-Net layer. It consumes the Page Element Registry plus image-recognition, visual-text, table-normalizer, and embedding-candidate artifacts and emits conservative visual element records.

It classifies pages as figure, chart, diagram, illustrated parts list, callout/visual region, or visual page candidate. It also extracts figure references, sheet references, item/callout labels, and part-number candidates where present.

## Safety contract

Visual records are retrieval-only in v1.

They can:

- route retrieval,
- plan graph attachment,
- request OCR/catalog/graph comparison,
- identify candidate callouts and part numbers,
- mark pages for human review.

They cannot:

- answer directly,
- prove claims,
- mutate source truth,
- enter final answers as visual proof,
- override citation/trust/authority gates.

## Build

```bash
python scripts/build_trace_net_figure_chart_understanding_v1.py \
  --page-registry local_data/organization/trace_net/page_element_registry/trace_net_page_element_registry_v1.json \
  --image-recognition-audit local_data/organization/image_recognition/page_image_recognition_audit.json \
  --image-recognition-quality local_data/organization/image_recognition/page_image_recognition_quality.json \
  --visual-text-records local_data/organization/visual_text/visual_text_extraction_clean.jsonl \
  --visual-text-summary local_data/organization/visual_text/visual_text_clean_summary.json \
  --embedding-candidates local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json \
  --table-cell-normalizer local_data/organization/trace_net/table_cell_normalizer/trace_net_table_cell_normalizer_v1.json \
  --output-dir local_data/organization/trace_net/figure_chart_understanding \
  --require-page-registry-count 509 \
  --min-visual-records 100 \
  --min-visual-candidate-pages 100 \
  --min-figure-diagram-records 100 \
  --min-visual-regions 100 \
  --min-retrieval-only-records 100 \
  --min-graph-attachment-plans 100 \
  --quality
```

The thresholds above are conservative enough for local artifacts that include hundreds of visual/figure signals. If a smaller pilot artifact is used, lower the minimums.

## Quality check

```bash
python scripts/check_trace_net_figure_chart_understanding_v1_quality.py \
  --report-path local_data/organization/trace_net/figure_chart_understanding/trace_net_figure_chart_understanding_v1.json \
  --require-page-registry-count 509 \
  --min-visual-records 100 \
  --min-visual-candidate-pages 100 \
  --min-figure-diagram-records 100 \
  --min-visual-regions 100 \
  --min-retrieval-only-records 100 \
  --min-graph-attachment-plans 100 \
  --write-json
```

## Outputs

```text
local_data/organization/trace_net/figure_chart_understanding/
  trace_net_figure_chart_understanding_v1.json
  trace_net_figure_chart_understanding_v1_records.jsonl
  trace_net_figure_chart_understanding_v1_regions.jsonl
  trace_net_figure_chart_understanding_v1_callouts.jsonl
  trace_net_figure_chart_understanding_v1_graph_attachment_plan.jsonl
  trace_net_figure_chart_understanding_v1_summary.json
  trace_net_figure_chart_understanding_v1_manifest.json
  trace_net_figure_chart_understanding_v1_quality.json
  trace_net_figure_chart_understanding_v1.md
  trace_net_figure_chart_understanding_v1.html
```

## TRACE-Net placement

```text
Page Element Registry
  -> Figure / Chart / Diagram Understanding
  -> Universal Fishnet Retry
  -> Element Graph Attachment
```

Leiden/community detection is intentionally left as `pending_graph_community_pass`; it should run after visual elements are attached to the graph.
