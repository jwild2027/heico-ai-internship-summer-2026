# TRACE-Net Engineering Answer Runner v1

H5 chains the engineering-brain stages into one local command:

1. H2 engineering query planner
2. H3 engineering answer context pack
3. H4 engineering answer composer and quality gate

The runner preserves the context-engineering split:

- `guidance_context`: v2 summaries and planner hints only; not proof.
- `proof_context`: source-trace-ready visual/OCR/table records used for claims.

Safety contract: no Postgres writes, no Qdrant writes, no OpenSearch writes/uploads, no source-truth mutation, and no answer permission.
