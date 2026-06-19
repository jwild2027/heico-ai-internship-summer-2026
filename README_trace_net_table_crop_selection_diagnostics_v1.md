# TRACE-Net Table Crop Selection Diagnostics v1

Read-only diagnostic module for inspecting why Table Line Geometry selected either whole-page morphology or table-region crop morphology.

## Purpose

This module compares the 7 crop-selected cards against the 13 page-selected cards after OCR-enriched bbox routing. It helps tune future crop scoring without changing source truth or answer authority.

## Inputs

- `local_data/organization/trace_net/table_line_geometry/trace_net_table_line_geometry_v1.json`
- Optional `local_data/organization/trace_net/table_bbox_resolver/trace_net_table_bbox_resolver_v1.json`
- Optional `local_data/organization/trace_net/table_ocr_bbox_enrichment/trace_net_table_ocr_bbox_enrichment_v1.json`

## Outputs

- `trace_net_table_crop_selection_diagnostics_v1.json`
- `trace_net_table_crop_selection_diagnostics_v1_cards.jsonl`
- `trace_net_table_crop_selection_diagnostics_v1_summary.json`
- `trace_net_table_crop_selection_diagnostics_v1_quality.json`
- `trace_net_table_crop_selection_diagnostics_v1_manifest.json`

## Safety contract

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- no claim-proof authority
- diagnostics are advisory only
