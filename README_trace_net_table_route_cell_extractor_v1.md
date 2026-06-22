# TRACE-Net Table Route Cell Extractor v1

Read-only table-route data extraction stage for TRACE-Net.

This current-state patch adds v5 template-aware parsing on top of the Step 0 full-page bbox table route extraction path.

## Purpose

The module reads extraction-ready table records from `table_full_enclosure_bbox_reconstructor`, selects OCR sidecars, groups OCR tokens into rows/cells/values, and now labels recurring table templates so later normalizers can apply table-family-specific field rules.

## Current behavior

- Processes only records where `full_table_enclosure_bbox_ready=true` and `table_bbox_review_only=false`.
- Skips review-only/image-like records.
- Prefers token/word-level raw OCR sidecars such as TSV/hOCR over line OCR and derived matcher sidecars.
- Groups OCR tokens into row records, cell records, and value records.
- Adds advisory template labels:
  - `part_number_coverage_list`
  - `list_of_effective_pages`
  - `ipl_split_column_table`
  - `generic_table`
- Adds template roles to rows/cells/values, such as `covered_part_number`, `manual_page_reference`, `fig_item_or_quantity`, and `header`.

## Safety contract

This module is retrieval/evidence preparation only.

- No Postgres writes.
- No Qdrant writes.
- No OpenSearch writes.
- No source-truth mutation.
- No answer permission.
- No claim-proof authority.

## Typical build

```bash
python scripts/build_trace_net_table_route_cell_extractor_v1.py \
  --table-full-enclosure-bbox-reconstructor local_data/organization/trace_net/table_full_enclosure_bbox_reconstructor/trace_net_table_full_enclosure_bbox_reconstructor_v1.json \
  --table-ocr-bbox-enrichment local_data/organization/trace_net/table_ocr_bbox_enrichment/trace_net_table_ocr_bbox_enrichment_v1.json \
  --table-bbox-scoped-cell-extraction local_data/organization/trace_net/table_bbox_scoped_cell_extraction/trace_net_table_bbox_scoped_cell_extraction_v1.json \
  --ocr-root local_data/organization/trace_net/table_ocr_bbox_sidecars \
  --output-dir local_data/organization/trace_net/table_route_cell_extractor \
  --max-ocr-files-per-table 50 \
  --ocr-file-selection best \
  --max-rows-per-table 250 \
  --allow-legacy-fallback \
  --quality
```

## Outputs

- `trace_net_table_route_cell_extractor_v1.json`
- `trace_net_table_route_cell_extractor_v1_records.jsonl`
- `trace_net_table_route_cell_extractor_v1_rows.jsonl`
- `trace_net_table_route_cell_extractor_v1_cells.jsonl`
- `trace_net_table_route_cell_extractor_v1_values.jsonl`
- `trace_net_table_route_cell_extractor_v1_summary.json`
- `trace_net_table_route_cell_extractor_v1_quality.json`
- `trace_net_table_route_cell_extractor_v1_manifest.json`
