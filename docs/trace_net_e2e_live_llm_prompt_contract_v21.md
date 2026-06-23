# TRACE-Net E2E Live LLM Prompt Contract v21

Hotfix v21.1 cleans the LLM prompt contract before live LLM draft integration.

## Fixes

- Maps v20 `self_rag_crag_records` into the prompt so `SELF-RAG / CRAG STATUS` is not empty.
- Deduplicates source-truth evidence by page, field, and value before it reaches the LLM.
- Preserves duplicate counts with `occurrence_count` and contiguous citation numbering after dedupe.
- Separates direct source-truth evidence from nearby source-truth/OCR context.
- Keeps graph/Leiden and v2 summaries as guidance only.
- Keeps aggregation/capping metadata compact and explicit when group counts are truncated for prompt size.

## Contract

This stage builds LLM-ready prompt messages but does not call an LLM. The LLM reads compact context packs, not raw 5TB corpus data or the full graph. Source-truth evidence is the only proof authority. Graph/Leiden, v2 summaries, route metadata, vector hints, nearby OCR context, and aggregation metadata are guidance/disclosure layers only. A final gate is required after any LLM draft.
