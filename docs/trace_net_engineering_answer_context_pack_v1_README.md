# TRACE-Net Engineering Answer Context Pack v1

This module builds the first combined engineering context pack from an engineering query planner result.

It keeps two strict buckets:

- `guidance_context`: v2 summaries and planner hints. These are guidance only and cannot prove answer claims.
- `proof_context`: source-trace-ready visual, OCR nomenclature, and table/OCR records that can support factual claims.

Safety contract:

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes/uploads
- no source-truth mutation
- no answer permission

The context pack is intended for a later engineering answer composer and quality gate.
