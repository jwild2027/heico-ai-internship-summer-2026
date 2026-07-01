# TRACE-Net Fishnet Accepted Route Manifest v1

Builds a new accepted route manifest artifact from the fishnet route-manifest overlay.

This is the first “send accepted pages to their routes” step. It applies reviewed overlay
recommendations into a new manifest artifact, but it does not overwrite the official/current
route manifest.

Safety:
- no source-truth mutation
- no answer permission
- no Postgres/Qdrant/OpenSearch writes
- official route manifest is not mutated
- route changes require explicit `--accept-reviewed-overlays`
