# TRACE-Net Table OCR BBox Enrichment v1

Read-only TRACE-Net module that consumes OCR bbox sidecars for table pages and proposes advisory table-region crop boxes.

## Current upgrade: prefer `table_extraction_bbox`

This version makes `table_ocr_bbox_enrichment` prefer a safe upstream `table_extraction_bbox` from `table_line_geometry` before falling back to a fresh OCR-token bbox union. OCR-derived bbox fields remain recorded for audit and fallback, but the route-approved extraction crop is now the primary candidate when present and valid.

New card fields include:

- `ocr_inferred_table_region_bbox`
- `ocr_bbox_source`
- `ocr_bbox_confidence`
- `ocr_crop_candidate_ready`
- `table_extraction_bbox_candidate`
- `table_extraction_bbox_available`
- `table_extraction_bbox_valid`
- `table_extraction_bbox_preferred`
- `table_extraction_bbox_source_container`
- `table_extraction_bbox_source_key`
- `table_extraction_bbox_source`
- `table_extraction_bbox_confidence`
- `table_extraction_bbox_coverage_ratio`
- `table_extraction_bbox_rejection_reason`
- `bbox_preference_order`

Summary counters include:

- `table_extraction_bbox_available_card_count`
- `table_extraction_bbox_valid_card_count`
- `table_extraction_bbox_preferred_card_count`
- `table_extraction_bbox_consumed_card_count`
- `ocr_fallback_used_card_count`

## Current upgrade: OCR content-band tightening

This version still tightens broad OCR crop candidates before they reach the bbox resolver. When a raw OCR-token union covers most of the scanned page, the module computes a denser OCR content band by trimming outlier header/footer/marginal tokens with percentile-based bounds.

The original union remains recorded for audit.

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
