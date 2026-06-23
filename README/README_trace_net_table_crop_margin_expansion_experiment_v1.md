# TRACE-Net Table Crop Margin Expansion Experiment v1

Read-only diagnostic module that tests whether expanded table-region crop boxes recover stronger morphology evidence than the current page-level table morphology result.

## Purpose

The table pipeline now has OCR-derived and content-band tightened crop boxes, but page-level morphology still wins for all 20 table cards. This module runs a controlled margin sweep around the current table bbox and records whether expanded crops improve vertical line or intersection evidence.

## Inputs

- `table_line_geometry/trace_net_table_line_geometry_v1.json`
- `table_bbox_resolver/trace_net_table_bbox_resolver_v1.json`
- resolved TIFF/page images under `--image-root`

## Outputs

- `trace_net_table_crop_margin_expansion_experiment_v1.json`
- `trace_net_table_crop_margin_expansion_experiment_v1_cards.jsonl`
- `trace_net_table_crop_margin_expansion_experiment_v1_summary.json`
- `trace_net_table_crop_margin_expansion_experiment_v1_quality.json`
- `trace_net_table_crop_margin_expansion_experiment_v1_manifest.json`

## Safety contract

This module is advisory only.

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- no claim-proof authority
