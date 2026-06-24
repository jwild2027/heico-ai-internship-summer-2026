# TRACE-Net Route Brain Image Page Audit v35.1

This module audits the route brain against a manually screened diagram-page set. It fixes the immediate image-route problem by distinguishing route-manifest `image_visual` candidates from actual diagram/drawing/callout pages.

The module does not mutate source truth and does not grant answer permission. It writes audit/correction artifacts that downstream visual context builders can use.

Outputs:

- `trace_net_route_brain_image_page_audit_v35_1.json`
- `trace_net_actual_diagram_pages_v35_1.jsonl`
- `trace_net_route_brain_corrections_v35_1.jsonl`
- `trace_net_overbroad_image_visual_candidates_v35_1.jsonl`
- `trace_net_missed_diagram_pages_v35_1.jsonl`

Key behavior:

- Actual diagram/image pages come from `manual_screened_diagram_pages_v0.csv`.
- Existing route manifest is still inspected, but no longer trusted alone for actual diagram count.
- Overbroad `image_visual` pages are demoted to review/non-diagram, not treated as diagram pages.
- Nested route policy JSON objects are parsed safely instead of being stringified into route names.


Hotfix note: route parser treats nested route policy objects as normal manifest structure, not malformed route values. Script wrappers add repo root to sys.path for direct CLI use.
