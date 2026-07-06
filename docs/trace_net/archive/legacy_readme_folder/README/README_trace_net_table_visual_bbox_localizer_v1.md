# TRACE-Net Table Visual BBox Localizer v1

Read-only visual table-localization refinement for TRACE-Net table extraction.

## Purpose

The previous table-route patches proved that `table_extraction_bbox` is selected, preferred by OCR bbox enrichment, and consumed by the bbox-scoped row/cell bridge. They did **not** prove that the bbox is visually tight around the table.

This module fixes that gap by inspecting the source page image inside the preferred bbox and refining the crop around table-like visual structure:

- dark-pixel content extent,
- horizontal line runs,
- vertical line runs,
- row-band density,
- column-band density,
- page-coverage tightness.

It outputs a `localized_table_bbox` for downstream table extraction and records QA flags when the crop still looks too broad or visually weak.

## Safety contract

This module is local-artifact only:

- no Postgres writes,
- no Qdrant writes,
- no OpenSearch writes,
- no source-truth mutation,
- no answer permission,
- no claim-proof authority.

Every record is routing/retrieval-only.

## Inputs

- `local_data/organization/trace_net/table_ocr_bbox_enrichment/trace_net_table_ocr_bbox_enrichment_v1.json`
- Source page images resolvable from card image paths or by scanning `--image-root` for page IDs.

## Outputs

- `trace_net_table_visual_bbox_localizer_v1.json`
- `trace_net_table_visual_bbox_localizer_v1_records.jsonl`
- `trace_net_table_visual_bbox_localizer_v1_summary.json`
- `trace_net_table_visual_bbox_localizer_v1_quality.json`
- `trace_net_table_visual_bbox_localizer_v1_manifest.json`

## Why this exists

A bbox can be valid, preferred, and consumed while still covering too much of the page. This module adds the missing visual-localization step so downstream row/cell/value extraction can prefer a tighter `localized_table_bbox` instead of blindly trusting broad OCR/page-content crops.

## v2 tightening focus

This current-state patch tightens the failure mode visible near the bottom of the overlay contact sheet: split-column IPC/manual pages where long vertical rules and footer/page-number furniture can make the crop too narrow, too tall, or biased to one column group.

Additional diagnostics include:

- `split_column_geometry_merged_record_count`
- `footer_page_furniture_suppressed_record_count`
- per-record `multi_column_vertical_merge_applied`
- per-record `footer_suppression_applied`
- review flags `split_column_table_geometry_merged` and `footer_page_furniture_suppressed`

The module still stays conservative. It merges separated vertical-rule clusters only when the combined span looks table-like rather than page-wide, and it suppresses bottom furniture only when repeated structural rows identify the table body.
