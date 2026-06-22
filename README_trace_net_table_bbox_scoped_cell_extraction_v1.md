# TRACE-Net Table BBox Scoped Cell Extraction v1

This module is a downstream table consumer for the current TRACE-Net table route. It joins existing `table_understanding` row/cell/value records with the preferred `table_extraction_bbox` crop selected by `table_ocr_bbox_enrichment`.

## Purpose

The table route now has a visually inspectable Paddle-style extraction bbox. The previous enrichment patch made `table_ocr_bbox_enrichment` prefer that bbox. This module creates the next downstream bridge artifact: rows, cells, and cell-value records are explicitly scoped to the selected table crop.

## Inputs

- `local_data/organization/trace_net/table_understanding/trace_net_table_understanding_v1.json`
- `local_data/organization/trace_net/table_ocr_bbox_enrichment/trace_net_table_ocr_bbox_enrichment_v1.json`

## Outputs

Written under `local_data/organization/trace_net/table_bbox_scoped_cell_extraction/`:

- `trace_net_table_bbox_scoped_cell_extraction_v1.json`
- `trace_net_table_bbox_scoped_cell_extraction_v1_records.jsonl`
- `trace_net_table_bbox_scoped_cell_extraction_v1_values.jsonl`
- `trace_net_table_bbox_scoped_cell_extraction_v1_legacy_unscoped_records.jsonl`
- `trace_net_table_bbox_scoped_cell_extraction_v1_summary.json`
- `trace_net_table_bbox_scoped_cell_extraction_v1_quality.json`
- `trace_net_table_bbox_scoped_cell_extraction_v1_manifest.json`

## Safety contract

This module is read-only with respect to TRACE-Net source truth and service stores:

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no direct answer permission
- no claim-proof authority

## Quality intent

A PASS run should show that the bbox-enriched route-table target set has downstream row/cell/value evidence scoped to the preferred `table_extraction_bbox` crop, while safety counters remain zero. Historical `table_understanding` records that do not have a matching route-table bbox enrichment card are preserved as legacy unscoped/pass-through diagnostics and are not counted as strict bbox-scope failures.
