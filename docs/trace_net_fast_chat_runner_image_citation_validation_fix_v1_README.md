# TRACE-Net Fast Chat Runner Image Citation Validation Fix v1

This focused fix teaches the main fast chat runner that image-route `V*` citations are valid when, and only when, the image route adapter and image route quality gate have already verified linked, source-traced visual evidence.

The previous image-route integration reached `query_type=image_or_diagram`, selected the adapter, and passed the image route quality gate, but the old generic citation validator still marked `V6` as invalid because it only understood older citation namespaces.

This patch inserts a guarded image-route citation validation block before the runner's generic `_quality_status(...)` call.

Safety contract:

- No Postgres writes.
- No Qdrant writes.
- No OpenSearch writes/uploads.
- No source-truth mutation.
- No answer permission.
- LLaVA-only part identity remains blocked.
