# TRACE-Net Fishnet Route Manifest Overlay v1

Read-only route-manifest overlay builder for fishnet router hardening policy records.

## Purpose

This module converts `normal_text_review_promotion` policy records into a proposed route overlay artifact. It validates recommendations against the current route manifest using page-id aliases such as `source_p000004` and `t_p_120_1176_p000004`.

## Safety contract

- Does not mutate the official route manifest.
- Does not authorize route changes.
- Does not write to Postgres, Qdrant, or OpenSearch.
- Does not mutate source truth.
- Does not grant answer permission.
- Produces review-only overlay records.

## Outputs

- `trace_net_fishnet_route_manifest_overlay_v1.json`
- `trace_net_fishnet_route_manifest_overlay_v1_records.jsonl`
- `trace_net_fishnet_route_manifest_overlay_v1_summary.json`
- `trace_net_fishnet_route_manifest_overlay_v1_quality.json`
- `trace_net_fishnet_route_manifest_overlay_v1.md`
