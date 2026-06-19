# TRACE-Net Table OCR BBox Enrichment v1

Read-only TRACE-Net module that consumes OCR bbox sidecars for table pages and proposes advisory table-region crop boxes.

## Current upgrade: OCR content-band tightening

This version tightens broad OCR crop candidates before they reach the bbox resolver. When a raw OCR-token union covers most of the scanned page, the module computes a denser OCR content band by trimming outlier header/footer/marginal tokens with percentile-based bounds. The original union remains recorded for audit.

New fields include:

- `original_inferred_table_region_bbox`
- `original_bbox_coverage_ratio`
- `content_band_bbox`
- `content_band_bbox_coverage_ratio`
- `content_band_tightening_available`
- `content_band_tightening_applied`
- `content_band_tightening_reason`
- `content_band_source_record_count`
- `content_band_selected_record_count`

Summary counters include:

- `content_band_tightening_available_card_count`
- `content_band_tightening_applied_card_count`
- `broad_ocr_bbox_card_count`
- `tightened_ocr_bbox_card_count`

## Safety contract

- No Postgres writes.
- No Qdrant writes.
- No OpenSearch writes.
- No source-truth mutation.
- No answer permission.
- No claim-proof authority.
- BBoxes are advisory crop metadata only.

## Inputs

- `--table-line-geometry local_data/organization/trace_net/table_line_geometry/trace_net_table_line_geometry_v1.json`
- `--table-cell-normalizer local_data/organization/trace_net/table_cell_normalizer/trace_net_table_cell_normalizer_v1.json`
- `--table-image-resolver local_data/organization/trace_net/table_image_resolver/trace_net_table_image_resolver_v1.json`
- `--table-bbox-resolver local_data/organization/trace_net/table_bbox_resolver/trace_net_table_bbox_resolver_v1.json`
- `--ocr-root local_data/organization/trace_net/table_ocr_bbox_sidecars`
- `--image-root .`

## Outputs

Under `local_data/organization/trace_net/table_ocr_bbox_enrichment/`:

- `trace_net_table_ocr_bbox_enrichment_v1.json`
- `trace_net_table_ocr_bbox_enrichment_v1_cards.jsonl`
- `trace_net_table_ocr_bbox_enrichment_v1_summary.json`
- `trace_net_table_ocr_bbox_enrichment_v1_quality.json`
- `trace_net_table_ocr_bbox_enrichment_v1_manifest.json`

## Build

```bash
python scripts/build_trace_net_table_ocr_bbox_enrichment_v1.py \
  --table-line-geometry local_data/organization/trace_net/table_line_geometry/trace_net_table_line_geometry_v1.json \
  --table-cell-normalizer local_data/organization/trace_net/table_cell_normalizer/trace_net_table_cell_normalizer_v1.json \
  --table-image-resolver local_data/organization/trace_net/table_image_resolver/trace_net_table_image_resolver_v1.json \
  --table-bbox-resolver local_data/organization/trace_net/table_bbox_resolver/trace_net_table_bbox_resolver_v1.json \
  --ocr-root local_data/organization/trace_net/table_ocr_bbox_sidecars \
  --image-root . \
  --output-dir local_data/organization/trace_net/table_ocr_bbox_enrichment \
  --max-ocr-files-scanned 25000 \
  --min-source-cards 1 \
  --min-enrichment-cards 1 \
  --min-crop-candidate-cards 1 \
  --max-unsafe-enrichment-cards 0 \
  --max-answer-permission-count 0 \
  --max-source-truth-mutation-allowed 0 \
  --require-table-line-geometry-quality-pass \
  --require-table-image-resolver-quality-pass \
  --require-table-bbox-resolver-quality-pass \
  --require-no-answer-permission \
  --quality
```

## Quality check

```bash
python scripts/check_trace_net_table_ocr_bbox_enrichment_v1_quality.py \
  --report-path local_data/organization/trace_net/table_ocr_bbox_enrichment/trace_net_table_ocr_bbox_enrichment_v1.json \
  --min-source-cards 1 \
  --min-enrichment-cards 1 \
  --min-crop-candidate-cards 1 \
  --max-unsafe-enrichment-cards 0 \
  --max-answer-permission-count 0 \
  --max-source-truth-mutation-allowed 0 \
  --require-table-line-geometry-quality-pass \
  --require-table-image-resolver-quality-pass \
  --require-table-bbox-resolver-quality-pass \
  --require-no-answer-permission \
  --write-json
```
