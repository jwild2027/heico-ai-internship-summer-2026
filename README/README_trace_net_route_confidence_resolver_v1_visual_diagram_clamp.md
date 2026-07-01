# TRACE-Net Route Confidence Resolver v1 Visual Diagram Clamp

This focused patch tightens `trace_net_route_confidence_resolver_v1` so generic IPL/table terms do not route pages to `image_visual_diagram`.

## Why

After the front-matter clamp, `cover_or_title_page` dropped correctly, but `image_visual_diagram` rose too high because terms such as `FIG`, `ITEM`, `VIEW`, `PARTS LIST`, `ASSY NUMBER`, and `CH-SEC-UN-FIG` can appear in structured IPL pages. Those are not sufficient proof that a page is a diagram.

## Behavior

`image_visual_diagram` now requires one of:

- upstream legacy `image_visual` route with sparse text, or
- concrete sparse visual labels such as seat/backrest/belt/fastener/skin-ply/vacuum/tape terms, with no strong IPL/table blocker.

Generic IPL visual references are ignored unless concrete diagram evidence exists.

## Safety

No Postgres writes. No Qdrant writes. No OpenSearch writes. No source-truth mutation. No answer permission.
