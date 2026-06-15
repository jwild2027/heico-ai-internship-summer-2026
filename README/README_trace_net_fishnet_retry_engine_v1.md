# TRACE-Net Universal Fishnet Retry Engine v1

This module builds a read-only, per-page fishnet retry and review plan across TRACE-Net extractor families.

It connects the front-start TRACE-Net chain:

```text
Page
  -> classify page traits
  -> choose extraction route
  -> run specialized extractors
  -> retry failures through fishnet layers
  -> compare outputs against OCR/catalog/graph
  -> assign trust tier
  -> attach clean evidence to graph
```

## What this module does

It reads existing artifacts:

```text
local_data/organization/trace_net/page_element_registry/trace_net_page_element_registry_v1.json
local_data/organization/trace_net/table_cell_normalizer/trace_net_table_cell_normalizer_v1.json
local_data/organization/trace_net/figure_chart_understanding/trace_net_figure_chart_understanding_v1.json
local_data/organization/trace_net/visual_ink_layout_calibrator/trace_net_visual_ink_layout_calibrator_v1.json
local_data/organization/trace_net/evidence_consensus/evidence_consensus_summary.json
```

Then it writes one fishnet retry plan per page under:

```text
local_data/organization/trace_net/fishnet_retry_engine/
```

## What fishnet means

Fishnet means weak extraction results get caught by another validation layer instead of being trusted or ignored.

The layers are:

```text
Layer 0: normal extraction inventory
Layer 1: OCR cleanup and sparse-page validation
Layer 2: region/tile/cell retry
Layer 3: specialized extractor retry
Layer 4: OCR/catalog/graph/source/citation comparison
Layer 5: trust downgrade, block, or human review
```

## Safety contract

Fishnet retry records are route/review metadata only.

They cannot:

```text
answer directly
prove claims
mutate source truth
allow final answers
```

They can:

```text
recommend OCR retry
recommend table-cell validation
recommend visual/callout retry
recommend catalog/graph comparison
recommend human review
recommend trust downgrade/blocking
```

## Build

```bash
python scripts/build_trace_net_fishnet_retry_engine_v1.py \
  --page-registry local_data/organization/trace_net/page_element_registry/trace_net_page_element_registry_v1.json \
  --table-cell-normalizer local_data/organization/trace_net/table_cell_normalizer/trace_net_table_cell_normalizer_v1.json \
  --figure-chart-understanding local_data/organization/trace_net/figure_chart_understanding/trace_net_figure_chart_understanding_v1.json \
  --visual-ink-layout-calibrator local_data/organization/trace_net/visual_ink_layout_calibrator/trace_net_visual_ink_layout_calibrator_v1.json \
  --evidence-consensus-summary local_data/organization/trace_net/evidence_consensus/evidence_consensus_summary.json \
  --output-dir local_data/organization/trace_net/fishnet_retry_engine \
  --require-page-count 509 \
  --min-fishnet-records 509 \
  --min-pages-with-retry-plan 509 \
  --min-pages-with-review-or-retry 1 \
  --min-extractor-family-count 6 \
  --min-table-retry-actions 1 \
  --min-visual-retry-actions 1 \
  --min-ocr-retry-actions 1 \
  --quality
```

## Quality check

```bash
python scripts/check_trace_net_fishnet_retry_engine_v1_quality.py \
  --report-path local_data/organization/trace_net/fishnet_retry_engine/trace_net_fishnet_retry_engine_v1.json \
  --require-page-count 509 \
  --min-fishnet-records 509 \
  --min-pages-with-retry-plan 509 \
  --min-pages-with-review-or-retry 1 \
  --min-extractor-family-count 6 \
  --min-table-retry-actions 1 \
  --min-visual-retry-actions 1 \
  --min-ocr-retry-actions 1 \
  --write-json
```

## Outputs

```text
trace_net_fishnet_retry_engine_v1.json
trace_net_fishnet_retry_engine_v1_records.jsonl
trace_net_fishnet_retry_engine_v1_actions.jsonl
trace_net_fishnet_retry_engine_v1_routes.jsonl
trace_net_fishnet_retry_engine_v1_summary.json
trace_net_fishnet_retry_engine_v1_manifest.json
trace_net_fishnet_retry_engine_v1_quality.json
trace_net_fishnet_retry_engine_v1.md
trace_net_fishnet_retry_engine_v1.html
```

## What comes next

After this passes, the next step should be an executor or graph attachment layer:

```text
Step 17.1: Fishnet Retry Executor Pilot v1
```

or:

```text
Step 18: Element-to-Graph Attachment v1
```

The v1 engine is intentionally plan-only so TRACE-Net can audit retry decisions before running or mutating anything.
