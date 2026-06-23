# TRACE-Net Table Full Region Recovery v1

Read-only diagnostic/artifact builder for recovering fuller table regions from incomplete table crop candidates.

## Purpose

This stage targets the current table issue where crop overlays/candidates do not cover the full table. It unions existing table bbox candidates with OCR content bands and overlay detector bboxes, expands the result by a small margin, and emits an advisory `expanded_full_table_bbox` per table.

It does **not** grant answer permission, prove claims, mutate source truth, or write to Postgres/Qdrant/OpenSearch.

## Inputs

- `table_bbox_resolver`
- `table_ocr_bbox_enrichment`
- optional `table_detector_overlay_audit`
- optional `table_line_geometry`
- optional `image_root` for page dimension probing

## Outputs

- `trace_net_table_full_region_recovery_v1.json`
- `trace_net_table_full_region_recovery_v1_cards.jsonl`
- `trace_net_table_full_region_recovery_v1_summary.json`
- `trace_net_table_full_region_recovery_v1_quality.json`
- `trace_net_table_full_region_recovery_v1_manifest.json`

## Safety contract

- Read-only
- Advisory only
- No final answer authority
- No claim proof authority
- No source-truth mutation
- No database writes
