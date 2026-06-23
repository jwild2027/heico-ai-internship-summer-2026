# TRACE-Net Table Margin Detector Parity v1

Read-only diagnostic module for comparing production Table Line Geometry morphology against the lightweight margin-expansion estimator on identical table crop candidates.

## Purpose

The previous margin experiment showed many expanded crops improved grid evidence, but production Table Line Geometry did not select those crops. This module compares both detectors on the same page/table/bbox/margin inputs so we can determine whether production is too strict or the experiment is counting non-table strokes.

## Inputs

- `local_data/organization/trace_net/table_line_geometry/trace_net_table_line_geometry_v1.json`
- `local_data/organization/trace_net/table_bbox_resolver/trace_net_table_bbox_resolver_v1.json`
- resolved TIFF/page images under `--image-root`

## Outputs

- `trace_net_table_margin_detector_parity_v1.json`
- `trace_net_table_margin_detector_parity_v1_cards.jsonl`
- `trace_net_table_margin_detector_parity_v1_summary.json`
- `trace_net_table_margin_detector_parity_v1_quality.json`
- `trace_net_table_margin_detector_parity_v1_manifest.json`

## Safety contract

This module is advisory diagnostics only.

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- no claim-proof authority

## Typical build

```bash
python scripts/build_trace_net_table_margin_detector_parity_v1.py \
  --table-line-geometry local_data/organization/trace_net/table_line_geometry/trace_net_table_line_geometry_v1.json \
  --table-bbox-resolver local_data/organization/trace_net/table_bbox_resolver/trace_net_table_bbox_resolver_v1.json \
  --image-root . \
  --output-dir local_data/organization/trace_net/table_margin_detector_parity \
  --margin-pixels 0,25,50,100,150,250 \
  --min-parity-cards 20 \
  --min-margin-candidate-evaluations 120 \
  --min-successful-image-cards 20 \
  --min-detector-disagreement-cards 1 \
  --max-unsafe-parity-cards 0 \
  --max-answer-permission-count 0 \
  --max-source-truth-mutation-allowed 0 \
  --require-table-line-geometry-quality-pass \
  --require-table-bbox-resolver-quality-pass \
  --require-no-answer-permission \
  --quality
```
