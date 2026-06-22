# TRACE-Net E2E Self-RAG Context Critic v9

This module critiques dynamic context packs before they are handed to an LLM. It checks whether each pack has citation-ready source-truth evidence, whether evidence fields match the query intent, whether graph/summary/vector/route guidance is marked as guidance-only, and whether the rules box keeps answer/source-truth authority blocked.

## Contract

- Uses prebuilt v8 context packs only.
- Does not call an LLM.
- Does not rerun retrieval, OCR, page classification, embeddings, page summaries, graph build, table extraction, or source ingest.
- Treats the evidence box as the only source-truth/citable layer.
- Treats graph, summary, vector/profile, route, and table-route signals as guidance only.
- Emits statuses for prompt readiness, CRAG retry, and human review.

## Statuses

- `SELF_RAG_CONTEXT_READY`: ready for prompt contract construction.
- `SELF_RAG_CONTEXT_WEAK`: usable but has warnings.
- `SELF_RAG_CONTEXT_NEEDS_CRAG_RETRY`: retrieval/context mismatch should go to CRAG correction.
- `SELF_RAG_CONTEXT_NEEDS_HUMAN_REVIEW`: unsafe authority or guidance/source-truth separation issue.
