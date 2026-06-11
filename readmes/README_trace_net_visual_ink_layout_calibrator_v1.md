# TRACE-Net Visual Ink / Layout Calibrator v1

Step 16.1 adds a math-based visual routing layer before any heavier image-recognition or vision model.

## Purpose

The figure/chart understanding layer is intentionally conservative and broad. It marks visual records as retrieval-only, but it can over-route front matter or text-heavy pages as chart/figure candidates. This calibrator uses deterministic image/layout metrics to refine those routes.

The algorithm is:

```text
page image audit metrics
  -> ink ratio
  -> line density
  -> connected component density
  -> largest component ratio
  -> table/grid score
  -> visual score
  -> page role/context/table evidence
  -> calibrated layout class
```

It does not read images directly. It uses the existing `page_image_recognition_audit.json` metrics, which were already produced by the image-recognition audit.

## Math features

- `ink_ratio`: dark pixels divided by sampled pixels.
- `line_density_score`: horizontal and vertical line counts normalized to a grid-like scale.
- `component_density_score`: log-scaled connected-component count.
- `largest_component_ratio`: largest dark component divided by total dark pixels.
- `table_score`: grid score plus line density and structured table rows.
- `diagram_score`: visual score plus component structure and parts/figure context.
- `chart_score`: visual score with chart-word support, penalized for table/front-matter/blank pages.
- `text_score`: OCR/source text/front-matter/procedure/revision signal.

## Safety boundary

The output is route-only:

```text
can_answer_directly = false
can_prove_claims = false
can_mutate_source_truth = false
visual_answer_allowed = false
requires_source_resolution = true
requires_citation = true
requires_authority_gate = true
```

## Build

```bash
python scripts/build_trace_net_visual_ink_layout_calibrator_v1.py \
  --page-registry local_data/organization/trace_net/page_element_registry/trace_net_page_element_registry_v1.json \
  --image-recognition-audit local_data/organization/image_recognition/page_image_recognition_audit.json \
  --figure-chart-understanding local_data/organization/trace_net/figure_chart_understanding/trace_net_figure_chart_understanding_v1.json \
  --table-cell-normalizer local_data/organization/trace_net/table_cell_normalizer/trace_net_table_cell_normalizer_v1.json \
  --output-dir local_data/organization/trace_net/visual_ink_layout_calibrator \
  --require-page-count 509 \
  --min-calibrated-pages 509 \
  --min-ink-metric-pages 509 \
  --min-blank-pages 14 \
  --min-reclassified-pages 1 \
  --quality
```

Optional stricter chart guard:

```bash
--max-chart-pages 80
```

## Quality

```bash
python scripts/check_trace_net_visual_ink_layout_calibrator_v1_quality.py \
  --report-path local_data/organization/trace_net/visual_ink_layout_calibrator/trace_net_visual_ink_layout_calibrator_v1.json \
  --require-page-count 509 \
  --min-calibrated-pages 509 \
  --min-ink-metric-pages 509 \
  --min-blank-pages 14 \
  --min-reclassified-pages 1 \
  --write-json
```

## Outputs

```text
local_data/organization/trace_net/visual_ink_layout_calibrator/
  trace_net_visual_ink_layout_calibrator_v1.json
  trace_net_visual_ink_layout_calibrator_v1_records.jsonl
  trace_net_visual_ink_layout_calibrator_v1_routes.jsonl
  trace_net_visual_ink_layout_calibrator_v1_summary.json
  trace_net_visual_ink_layout_calibrator_v1_manifest.json
  trace_net_visual_ink_layout_calibrator_v1_quality.json
  trace_net_visual_ink_layout_calibrator_v1.md
  trace_net_visual_ink_layout_calibrator_v1.html
```
