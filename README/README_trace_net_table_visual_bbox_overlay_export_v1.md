# TRACE-Net Table Visual BBox Overlay Export v1

This module exports PNG overlays and a contact sheet for `trace_net_table_visual_bbox_localizer_v1`.

It is an inspection/QA stage. It does not change source truth and does not grant answer authority.

## What it draws

- Amber rectangle: upstream/input bbox from the OCR bbox enrichment / prior localization path.
- Green rectangle: localized visual table bbox when the visual localizer quality-passed the record.
- Red rectangle: localized fallback bbox when the record did not quality-pass.

## Inputs

- `local_data/organization/trace_net/table_visual_bbox_localizer/trace_net_table_visual_bbox_localizer_v1.json`
- Source page images resolved from record `image_path` or by scanning `--image-root`.

## Outputs

Under `local_data/organization/trace_net/table_visual_bbox_overlay_export/`:

- `trace_net_table_visual_bbox_overlay_export_v1.json`
- `trace_net_table_visual_bbox_overlay_export_v1_records.jsonl`
- `trace_net_table_visual_bbox_overlay_export_v1_summary.json`
- `trace_net_table_visual_bbox_overlay_export_v1_quality.json`
- `trace_net_table_visual_bbox_overlay_export_v1_manifest.json`
- `trace_net_table_visual_bbox_localizer_overlay_contact_sheet_v1.png`
- `overlays/*.png`

## Safety contract

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- no claim-proof authority

## Example

```bash
python scripts/build_trace_net_table_visual_bbox_overlay_export_v1.py \
  --table-visual-bbox-localizer local_data/organization/trace_net/table_visual_bbox_localizer/trace_net_table_visual_bbox_localizer_v1.json \
  --image-root . \
  --output-dir local_data/organization/trace_net/table_visual_bbox_overlay_export \
  --min-source-records 20 \
  --min-overlay-records 20 \
  --min-image-available-records 20 \
  --min-overlay-pngs 20 \
  --min-contact-sheets 1 \
  --max-unsafe-records 0 \
  --max-answer-permission-count 0 \
  --max-source-truth-mutation-allowed 0 \
  --require-table-visual-bbox-localizer-quality-pass \
  --require-no-answer-permission \
  --quality
```
