# TRACE-Net Table Full Enclosure BBox Reconstructor v1

Read-only bbox reconstruction stage for TRACE-Net table routing.

This module consumes `table_structure_bbox_localizer` and `table_presence_verifier`. When presence verification recommends `full_table_enclosure_recommended=true`, the module reconstructs a conservative bbox from the safe input bbox plus available selected/visual bbox evidence. The goal is to encompass the whole table instead of trusting over-tight visual crops that may cut columns, rows, or header bands.

## Inputs

- `local_data/organization/trace_net/table_structure_bbox_localizer/trace_net_table_structure_bbox_localizer_v1.json`
- `local_data/organization/trace_net/table_presence_verifier/trace_net_table_presence_verifier_v1.json`

## Outputs

- `trace_net_table_full_enclosure_bbox_reconstructor_v1.json`
- `trace_net_table_full_enclosure_bbox_reconstructor_v1_records.jsonl`
- `trace_net_table_full_enclosure_bbox_reconstructor_v1_reconstructed_records.jsonl`
- `trace_net_table_full_enclosure_bbox_reconstructor_v1_summary.json`
- `trace_net_table_full_enclosure_bbox_reconstructor_v1_quality.json`
- `trace_net_table_full_enclosure_bbox_reconstructor_v1_manifest.json`

## Safety contract

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- no claim-proof authority

## Intended downstream use

Downstream row/cell extraction should prefer `full_table_enclosure_bbox` when `full_table_enclosure_bbox_ready=true`, especially for weak/challenged table-route records that need complete table containment.


## v2 boundary reconstruction tightening

This current-state patch keeps the module name/schema at `trace_net_table_full_enclosure_bbox_reconstructor_v1` but tightens behavior for the observed boundary failures:

- split-column/table-fragment records are expanded toward a full-table boundary instead of preserving top-left bias;
- visual candidates that cut columns, rows, or header bands remain rejected as extraction authority;
- weak route-table records can still proceed with a conservative full-table enclosure;
- diagram/image-like non-table candidates are preserved only as review bboxes and are not marked extraction-ready;
- all output remains retrieval/routing-only with no answer permission, proof authority, DB writes, or source-truth mutation.

## Step-0 full-page bbox mode

This current-state patch adds a temporary extraction-safety mode:

- pass `--force-final-bbox-full-page` with `--image-root` to resolve source page dimensions;
- extraction-ready table records receive `final_table_bbox_source=full_page_table_bbox`;
- `final_table_bbox` becomes the whole source page image bbox, for example `x0=0, y0=0, x1=image_width, y1=image_height`;
- review-only image/diagram-like records remain `table_bbox_review_only=true` and are not marked extraction-ready;
- new counters include `full_page_bbox_applied_record_count` and `full_page_bbox_unresolved_record_count`.

This is intentionally a conservative step-0 handoff for downstream table-route extraction: use the whole page first so row/cell extraction is not blocked by boundary errors, then tighten later from actual extracted rows/cells.
