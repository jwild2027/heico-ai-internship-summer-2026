# TRACE-Net Dublin Core Crosswalk Refinement v1 Type Tightening

This patch tightens public `dc:type` assignment in the refined Dublin Core crosswalk.

## Why

The first refinement split physical vs operational elements, but weak route/overlay signals could still promote broad public types. For example, a page with a generic `table` placeholder or page-level `visual_region` could appear as a real `table_page` or `visual_page` even when the stronger row/cell/callout evidence was absent.

## Change

Public Dublin Core types now require stronger evidence:

- `table_page` requires normalized rows, cells, repairs, or answer-support table-row candidates.
- `visual_page` requires callout or linked-part visual evidence, not only a generic visual region.
- `parts_page` requires explicit part-candidate or verified-part evidence.
- Weak table/visual signals are preserved as `trace_net:secondary_type_signals`.

The module remains read-only and does not mutate source truth, graph truth, Postgres, Qdrant, or OpenSearch.
