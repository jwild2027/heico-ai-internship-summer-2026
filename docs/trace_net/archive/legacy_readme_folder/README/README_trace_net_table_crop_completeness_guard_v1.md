# TRACE-Net Table Crop Completeness Guard v1

Read-only advisory guard for table crop completeness.

This stage exists because detector overlays showed that candidate crop boundaries can be incomplete or too page-like.  The guard decides whether a table crop is allowed to replace page morphology.  This revision also understands the `table_full_region_recovery` artifact, so recovered full-table crops can be allowed only when they are ready, not too page-like, and already produce real grid evidence in Table Line Geometry.

## Reads

- `local_data/organization/trace_net/table_line_geometry/trace_net_table_line_geometry_v1.json`
- `local_data/organization/trace_net/table_bbox_resolver/trace_net_table_bbox_resolver_v1.json`
- `local_data/organization/trace_net/table_detector_overlay_review_pack/trace_net_table_detector_overlay_review_pack_v1.json`
- optional: `local_data/organization/trace_net/table_full_region_recovery/trace_net_table_full_region_recovery_v1.json`

## Writes

- `trace_net_table_crop_completeness_guard_v1.json`
- `trace_net_table_crop_completeness_guard_v1_cards.jsonl`
- `trace_net_table_crop_completeness_guard_v1_summary.json`
- `trace_net_table_crop_completeness_guard_v1_quality.json`
- `trace_net_table_crop_completeness_guard_v1_manifest.json`

## What it checks

For each table crop candidate, the guard records whether crop selection should remain blocked or can be allowed.

It flags cases such as:

- detector disagreement without a safe human verdict
- estimator grid evidence still unreviewed
- crop bbox may be too small for a full-table crop
- recovered full-table bbox is too page-like
- recovered full-table bbox did not produce a grid signal
- no vertical table rules confirmed
- no table-rule intersections confirmed
- selected crop without a safe overlay verdict

Full-region recovery can unblock a crop only when explicitly enabled and all of these are true:

- `crop_recovery_ready` is true
- recovered bbox is not too page-like
- recovered bbox was used for the crop test in Table Line Geometry
- morphology signal is `GRID`
- vertical lines and intersections are present
- crop has vertical or intersection gain
- overlay verdict is not explicitly labeled text/noise

This unblocks crop morphology testing only.  It does not grant answer authority or proof authority.

## Safety contract

This module is advisory only:

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- cannot answer directly
- cannot prove claims

## Build with full-region recovery gate

```bash
python scripts/build_trace_net_table_crop_completeness_guard_v1.py \
  --table-line-geometry local_data/organization/trace_net/table_line_geometry/trace_net_table_line_geometry_v1.json \
  --table-bbox-resolver local_data/organization/trace_net/table_bbox_resolver/trace_net_table_bbox_resolver_v1.json \
  --overlay-review-pack local_data/organization/trace_net/table_detector_overlay_review_pack/trace_net_table_detector_overlay_review_pack_v1.json \
  --table-full-region-recovery local_data/organization/trace_net/table_full_region_recovery/trace_net_table_full_region_recovery_v1.json \
  --output-dir local_data/organization/trace_net/table_crop_completeness_guard \
  --min-completeness-cards 20 \
  --min-full-table-coverage-ratio 0.45 \
  --max-full-region-coverage-ratio 0.95 \
  --min-full-region-recovery-gate-allowed-cards 1 \
  --allow-full-region-recovery-ready-selection \
  --max-unsafe-completeness-cards 0 \
  --max-answer-permission-count 0 \
  --max-source-truth-mutation-allowed 0 \
  --require-table-line-geometry-quality-pass \
  --require-table-bbox-resolver-quality-pass \
  --require-overlay-review-pack-quality-pass \
  --require-table-full-region-recovery-quality-pass \
  --require-no-answer-permission \
  --quality
```

## Quality check

```bash
python scripts/check_trace_net_table_crop_completeness_guard_v1_quality.py \
  --report-path local_data/organization/trace_net/table_crop_completeness_guard/trace_net_table_crop_completeness_guard_v1.json \
  --min-completeness-cards 20 \
  --min-full-region-recovery-gate-allowed-cards 1 \
  --max-unsafe-completeness-cards 0 \
  --max-answer-permission-count 0 \
  --max-source-truth-mutation-allowed 0 \
  --require-table-line-geometry-quality-pass \
  --require-table-bbox-resolver-quality-pass \
  --require-overlay-review-pack-quality-pass \
  --require-table-full-region-recovery-quality-pass \
  --require-no-answer-permission \
  --write-json
```
