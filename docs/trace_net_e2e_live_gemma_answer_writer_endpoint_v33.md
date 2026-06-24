# TRACE-Net E2E Live Gemma Answer Writer Endpoint v33

v33 keeps the v32/v32.2 behavior where Gemma is always called through compact prompt packages, then adds deterministic Self-RAG/CRAG telemetry and a richer page-profile package.

## Adds in v33

- Self-RAG package-quality telemetry for every answer.
- CRAG retry/fallback telemetry for every answer.
- Richer page profile answers that combine source-truth page records with v2 summary guidance.
- Quality gates for `self_rag_sample_count`, `crag_sample_count`, and `crag_retry_required_count`.
- No new proof authority: source-truth records remain the only proof authority; graph, Leiden, v2 summaries, route metadata, and nomenclature metadata remain guidance only.

## Endpoint model

`trace-net-e2e-live-gemma-answer-writer-v33`

## Key telemetry

- `self_rag_status`
- `self_rag_package_quality`
- `self_rag_answerable_from_package`
- `self_rag_direct_source_truth_available`
- `self_rag_guidance_only_signals_present`
- `crag_status`
- `crag_retry_required`
- `crag_retry_reason`
- `crag_recommended_retry_route`
- `crag_fallback_safe`

## Safety contract

- Gemma is an answer writer, not proof authority.
- Final gate is always applied.
- Source truth is the only proof authority for factual claims.
- Graph/Leiden, v2 summaries, route metadata, and nomenclature metadata are guidance only.
- No source-truth mutation.
- No writes to Postgres, Qdrant, or OpenSearch.
