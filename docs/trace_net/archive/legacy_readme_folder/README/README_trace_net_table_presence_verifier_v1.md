# TRACE-Net Table Presence Verifier v1

Hybrid, read-only table-presence gate for TRACE-Net table localization.

This module prevents table localization from blindly trusting a candidate bbox. It combines route context, structure-localizer decisions, visual line/row/column diagnostics, bbox-scoped row/cell/value counts, OCR hints, and optional ink metrics. The v3 behavior also challenges `route_primary=table` when the table candidate is visually incomplete or over-tightened.

## v3 route-table challenge behavior

A table route is not treated as absolute proof. If a route-table candidate has strong evidence that a visual crop cuts columns, rows, header bands, or table extent, the page remains in the table workflow but is demoted from `confirmed_table` to `weak_table` and marked for conservative full-table enclosure reconstruction.

This protects downstream extraction from trusting tight partial bboxes while still preserving the table workflow for real table pages.

## Inputs

- `table_structure_bbox_localizer`
- optional `table_visual_bbox_localizer`
- optional `table_bbox_scoped_cell_extraction`
- optional `table_ocr_bbox_enrichment`
- optional `page_route_manifest`
- optional `route_dispatch_manifest`
- optional source images through `--image-root`

## Outputs

Under `local_data/organization/trace_net/table_presence_verifier/`:

- `trace_net_table_presence_verifier_v1.json`
- `trace_net_table_presence_verifier_v1_records.jsonl`
- `trace_net_table_presence_verifier_v1_allowed_table_records.jsonl`
- `trace_net_table_presence_verifier_v1_suppressed_candidates.jsonl`
- `trace_net_table_presence_verifier_v1_summary.json`
- `trace_net_table_presence_verifier_v1_quality.json`
- `trace_net_table_presence_verifier_v1_manifest.json`

## Key counters

- `confirmed_table_record_count`
- `weak_table_record_count`
- `not_table_record_count`
- `table_localization_allowed_record_count`
- `table_localization_suppressed_record_count`
- `table_route_challenged_count`
- `table_route_demoted_to_weak_count`
- `full_table_enclosure_recommended_count`
- `false_positive_table_candidate_count`

## Safety contract

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no direct answer permission
- no claim-proof authority
