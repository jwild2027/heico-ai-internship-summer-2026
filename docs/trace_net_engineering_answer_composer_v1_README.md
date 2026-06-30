# TRACE-Net Engineering Answer Composer v1

Builds an engineering-style answer from `trace_net_engineering_answer_context_pack_v1`.

The composer separates guidance from proof:

- `guidance_context` can frame or plan the answer, but is not proof.
- `proof_context` provides source-trace-ready evidence for claims.

Safety contract:

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes/uploads
- no source-truth mutation
- no answer permission

The quality gate checks citation validity, summary-as-proof use, LLaVA-only part identity claims, unsupported interchangeability/effectivity/fit/safety claims, and write/safety counters.
