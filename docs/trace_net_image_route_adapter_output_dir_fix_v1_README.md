# TRACE-Net Image Route Adapter Output Directory Fix v1

Fixes endpoint smoke/runtime calls where the fast chat runner invokes the image route adapter with a nested output directory that does not exist yet.

The adapter now creates `out_path.parent` before writing `trace_net_image_route_fast_chat_adapter_v1.json`.

Safety contract: artifact-only code path; no Postgres writes, no Qdrant writes, no OpenSearch writes/uploads, no source-truth mutation, no answer permission.
