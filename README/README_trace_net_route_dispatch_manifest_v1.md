# TRACE-Net Route Dispatch Manifest v1

Builds the dispatch layer that turns page route decisions into downstream processing permissions for every route family, not just tables.

Inputs:

- `trace_net_page_route_manifest_v1.json`

Outputs:

- `trace_net_route_dispatch_manifest_v1.json`
- `trace_net_route_dispatch_manifest_v1_quality.json`
- `trace_net_route_dispatch_manifest_v1_summary.json`

Each dispatch card contains route policies for:

- `table`
- `image_visual`
- `normal_text`
- `blank_candidate`
- `review`

Safety contract:

- no answer permission
- cannot answer directly
- cannot prove claims
- cannot mutate source truth
- no Postgres/Qdrant/OpenSearch writes

This module is the route-to-processing bridge. It does not execute downstream table/image/text processing itself.
