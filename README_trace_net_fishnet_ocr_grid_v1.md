# TRACE-Net Fishnet OCR Grid v1.5

Read-only fishnet/grid OCR signal builder for TRACE-Net router/classifier analysis.

## Purpose

This module builds spatial page evidence for scanned TIFF manuals without changing official routes. It splits each page into a fishnet grid, computes ink features, runs OCR, maps Tesseract TSV word boxes into grid cells, and emits candidate route signals for comparison/review.

## v1.5 change

v1.5 tightens table-vs-text scoring. v1.4 proved word boxes worked, but table scoring was too broad because dense OCR/list pages became `table`. v1.5 requires stronger structural table evidence and reports low-margin decisions as `review_required` instead of pretending they are confident route changes.

## Inputs

- Source package zip or unpacked directory containing TIFF/page images.
- Optional Tesseract executable path via `--tesseract-cmd`.

## Outputs

Written under the requested output directory:

- `trace_net_fishnet_ocr_grid_v1.json`
- `trace_net_fishnet_ocr_grid_v1_cards.jsonl`
- `trace_net_fishnet_ocr_grid_v1_summary.json`
- `trace_net_fishnet_ocr_grid_v1_quality.json`
- optional `overlays/`
- optional `trace_net_fishnet_ocr_grid_contact_sheet_v1.png`

## Safety contract

All records are router/classifier input only:

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no direct answer permission
- no claim-proof authority
- downstream source-truth confirmation required
