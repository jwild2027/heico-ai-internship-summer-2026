# TRACE-Net Table Image Resolver v1

`trace_net_table_image_resolver_v1` maps TRACE-Net table/page identifiers to local TIFF or page-image files so later table-geometry passes can run real morphological horizontal/vertical line detection.

## Purpose

Table Line Geometry v1 can already build OCR/table-normalizer fallback cards, but the current geometry artifact reports `image_line_detection_available: false` because page image paths are not available to the geometry cards. This resolver is the bridge:

```text
page_id / table_id
  -> explicit image fields from source artifacts
  -> context records from table normalizer / human review queue
  -> image-root filename scan
  -> selected local image path, confidence, and review flags
```

## Inputs

- `local_data/organization/trace_net/table_line_geometry/trace_net_table_line_geometry_v1.json`
- optional `local_data/organization/trace_net/table_cell_normalizer/trace_net_table_cell_normalizer_v1.json`
- optional `local_data/organization/trace_net/human_review_queue/trace_net_human_review_queue_v1.json`
- optional `--image-root` used to scan for `.tif`, `.tiff`, `.png`, `.jpg`, `.jpeg`, `.webp`, and `.bmp` page images

## Outputs

Written under `local_data/organization/trace_net/table_image_resolver/`:

- `trace_net_table_image_resolver_v1.json`
- `trace_net_table_image_resolver_v1_cards.jsonl`
- `trace_net_table_image_resolver_v1_summary.json`
- `trace_net_table_image_resolver_v1_quality.json`
- `trace_net_table_image_resolver_v1_manifest.json`

## Safety contract

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- no claim-proof authority
- image resolution is advisory and read-only

## Build

```bash
python scripts/build_trace_net_table_image_resolver_v1.py \
  --table-line-geometry local_data/organization/trace_net/table_line_geometry/trace_net_table_line_geometry_v1.json \
  --table-cell-normalizer local_data/organization/trace_net/table_cell_normalizer/trace_net_table_cell_normalizer_v1.json \
  --human-review-queue local_data/organization/trace_net/human_review_queue/trace_net_human_review_queue_v1.json \
  --image-root . \
  --output-dir local_data/organization/trace_net/table_image_resolver \
  --min-source-cards 1 \
  --min-resolver-cards 1 \
  --min-resolved-image-cards 0 \
  --max-unsafe-resolution-cards 0 \
  --max-answer-permission-count 0 \
  --max-source-truth-mutation-allowed 0 \
  --require-table-line-geometry-quality-pass \
  --require-no-answer-permission \
  --quality
```

`--min-resolved-image-cards` defaults to `0` because early local repos may not yet contain resolvable page images. If images are expected to be present, rerun with `--min-resolved-image-cards 1` or a higher threshold.

## Quality check

```bash
python scripts/check_trace_net_table_image_resolver_v1_quality.py \
  --report-path local_data/organization/trace_net/table_image_resolver/trace_net_table_image_resolver_v1.json \
  --min-source-cards 1 \
  --min-resolver-cards 1 \
  --min-resolved-image-cards 0 \
  --max-unsafe-resolution-cards 0 \
  --max-answer-permission-count 0 \
  --max-source-truth-mutation-allowed 0 \
  --require-table-line-geometry-quality-pass \
  --require-no-answer-permission \
  --write-json
```

## What comes next

Once this resolver can identify source page images, Table Line Geometry v1 can consume resolved image paths and run actual morphological line detection over the TIFF/page image.
