# TRACE-Net Table Structure BBox Localizer v1

`trace_net_table_structure_bbox_localizer_v1` is a read-only, containment-aware selector for table bounding boxes.

It sits after:

- `table_visual_bbox_localizer`
- `table_bbox_scoped_cell_extraction`

The previous visual localizer can create very tight boxes, but some tight boxes cut off columns, headers, or table body rows. This module uses a PaddleOCR / PP-Structure-style principle: table structure completeness matters more than visual tightness.

## What it does

For each visual table record, the module compares:

- the upstream safe input bbox,
- the visual localized bbox candidate,
- row/cell/value counts from bbox-scoped cell extraction,
- visual table signals such as horizontal/vertical line runs and row/column bands,
- split-column merge diagnostics.

The visual bbox replaces the input bbox only if it passes conservative containment checks:

- preserves enough width to avoid cutting table columns,
- preserves enough height to avoid cutting rows,
- is not overly aggressive by area ratio,
- keeps the top/header band,
- is tall enough for the row count,
- has enough row/column structure signal,
- has a matching bbox-scoped table/cell bridge record.

If any check fails, the module falls back to the upstream input bbox and records the rejection reason.

## Outputs

Default output directory:

```text
local_data/organization/trace_net/table_structure_bbox_localizer/
```

Main files:

- `trace_net_table_structure_bbox_localizer_v1.json`
- `trace_net_table_structure_bbox_localizer_v1_records.jsonl`
- `trace_net_table_structure_bbox_localizer_v1_summary.json`
- `trace_net_table_structure_bbox_localizer_v1_quality.json`
- `trace_net_table_structure_bbox_localizer_v1_manifest.json`

## Safety contract

This module is routing/evidence-preparation only.

It does not:

- write to Postgres,
- write to Qdrant,
- write to OpenSearch,
- mutate source truth,
- grant answer permission,
- prove claims.

## Intended next use

Downstream row/cell extraction should prefer:

```text
structure_selected_table_bbox
```

rather than directly trusting:

```text
localized_table_bbox
```

This prevents over-tight visual crops from becoming extraction authority.
