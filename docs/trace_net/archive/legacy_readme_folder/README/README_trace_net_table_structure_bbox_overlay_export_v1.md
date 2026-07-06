# TRACE-Net Table Structure BBox Overlay Export v1

Read-only QA exporter for the structure-first table bbox selector.

This module consumes `trace_net_table_structure_bbox_localizer_v1.json` and renders inspectable PNG overlays plus a contact sheet. It is intended to visually compare:

- amber: upstream/input bbox,
- blue/red: visual candidate bbox, blue when accepted and red when rejected,
- green: final structure-selected bbox.

If the structure selector falls back to the input bbox, the green box intentionally overlaps the amber box. That means the visual candidate was not trusted enough for downstream table extraction.

## Inputs

- `local_data/organization/trace_net/table_structure_bbox_localizer/trace_net_table_structure_bbox_localizer_v1.json`
- source page images resolved from record paths or by scanning `--image-root`

## Outputs

Under `local_data/organization/trace_net/table_structure_bbox_overlay_export/`:

- `trace_net_table_structure_bbox_overlay_export_v1.json`
- `trace_net_table_structure_bbox_overlay_export_v1_records.jsonl`
- `trace_net_table_structure_bbox_overlay_export_v1_summary.json`
- `trace_net_table_structure_bbox_overlay_export_v1_quality.json`
- `trace_net_table_structure_bbox_overlay_export_v1_manifest.json`
- `trace_net_table_structure_bbox_localizer_overlay_contact_sheet_v1.png`
- `overlays/*.png`

## Safety contract

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- no claim-proof authority

This is an inspection/export artifact only.
