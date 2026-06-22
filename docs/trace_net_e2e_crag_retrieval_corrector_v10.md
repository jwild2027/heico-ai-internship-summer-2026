# TRACE-Net E2E CRAG Retrieval Corrector v10

This module is Phase 3 of TRACE-Net context/reasoning work.

It consumes the Self-RAG context critic v9 artifact and emits corrective retrieval plans for each context pack. If Self-RAG marks a context as ready, v10 records that no retry is needed and the context can proceed to the prompt contract. If Self-RAG marks a context as weak, misrouted, missing citations, missing source trace, or unsafe, v10 creates a non-mutating corrective plan.

## Contract

The CRAG corrector is plan-only. It does not:

- call an LLM
- rerun retrieval
- rerun OCR
- rerun page classification
- rerun embeddings
- rebuild summaries
- rebuild graph/community artifacts
- rerun table extraction
- mutate source truth
- write to Postgres, Qdrant, OpenSearch, or other services

## Typical corrective actions

- `no_retry_required`
- `expand_source_truth_retrieval`
- `route_and_field_correction`
- `citation_repair`
- `guidance_authority_repair`
- `human_review_enqueue`
- `generic_retrieval_retry`

## Output

The build script writes:

- `trace_net_e2e_crag_retrieval_corrector_v10.json`
- `trace_net_e2e_crag_retrieval_corrector_plans_v10.jsonl`
- `trace_net_e2e_crag_retrieval_corrector_v10.md`

## Expected current behavior

For the current five passing dynamic context packs, Self-RAG v9 marks all contexts ready. Therefore v10 should produce five CRAG plans with `CRAG_NO_RETRY_NEEDED` and zero unsafe/write/answer-authority counters.
