# TRACE-Net Table Line Geometry v1

Read-only table geometry reconstruction for TRACE-Net.

This patch wires **Table Full Region Recovery v1** into Table Line Geometry as a guarded crop source.

## What changed

- Adds optional `--table-full-region-recovery` input.
- Loads `recovery_cards` from `trace_net_table_full_region_recovery_v1.json`.
- Uses `expanded_full_table_bbox` as the preferred crop candidate when:
  - `crop_recovery_ready` is true
  - the recovered bbox is parseable
  - the recovered bbox is not effectively full-page / page-like
  - dimensions meet minimum crop size
- Keeps normal safety gates:
  - page-vs-crop scoring still runs
  - crop completeness guard can still block selection
  - crop/margin morphology is advisory only
- Adds summary counters:
  - `table_full_region_recovery_available_card_count`
  - `table_full_region_recovery_ready_card_count`
  - `table_full_region_recovery_used_for_crop_card_count`
  - `table_full_region_recovery_crop_rejected_card_count`
  - `table_full_region_recovery_too_page_like_card_count`

## Safety

This module remains below the answer-authority line. It cannot answer directly, prove claims, mutate source truth, or write to Postgres/Qdrant/OpenSearch.

## Build example

```bash
python scripts/build_trace_net_table_line_geometry_v1.py \
  --table-cell-normalizer local_data/organization/trace_net/table_cell_normalizer/trace_net_table_cell_normalizer_v1.json \
  --table-image-resolver local_data/organization/trace_net/table_image_resolver/trace_net_table_image_resolver_v1.json \
  --table-bbox-resolver local_data/organization/trace_net/table_bbox_resolver/trace_net_table_bbox_resolver_v1.json \
  --table-full-region-recovery local_data/organization/trace_net/table_full_region_recovery/trace_net_table_full_region_recovery_v1.json \
  --table-crop-completeness-guard local_data/organization/trace_net/table_crop_completeness_guard/trace_net_table_crop_completeness_guard_v1.json \
  --image-root . \
  --output-dir local_data/organization/trace_net/table_line_geometry \
  --max-image-pages 50 \
  --min-table-geometry-cards 1 \
  --min-cell-records 100 \
  --min-image-line-detection-cards 1 \
  --min-table-region-crop-available-cards 1 \
  --min-table-region-crop-applied-cards 1 \
  --min-table-full-region-recovery-used-for-crop-cards 1 \
  --max-unsafe-geometry-cards 0 \
  --max-answer-permission-count 0 \
  --max-source-truth-mutation-allowed 0 \
  --require-table-image-resolver-quality-pass \
  --require-table-bbox-resolver-quality-pass \
  --require-table-full-region-recovery-quality-pass \
  --require-table-crop-completeness-guard-quality-pass \
  --require-image-line-detection \
  --require-no-answer-permission \
  --quality
```

## Crop completeness guard handoff fix

This revision treats `crop_selection_allowed=true` from the crop completeness guard as the authoritative gating decision for crop selection. If a guard card still carries advisory block/review context, Table Line Geometry no longer marks the same crop as blocked when the explicit allow flag is true. This lets full-region-recovered, grid-positive tables pass through the guard while keeping all non-allowed crops blocked.
