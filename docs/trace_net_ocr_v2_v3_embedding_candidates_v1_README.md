# TRACE-Net OCR + V2 + V3 Embedding Candidates v1

Builds one safe candidate bundle for Qdrant from:

- Fishnet OCR page cards
- Repaired/accepted Gemma V2 `page_context_v2` records
- V3 page intelligence cards

This builder does not call Ollama, does not create embeddings, and does not write to
Qdrant/Postgres/OpenSearch. It prepares loader-compatible candidate records.

Expected full corpus counts after current server run:

- OCR page candidates: 509
- V2 page context candidates: 506
- V3 page intelligence candidates: 509
- Total candidates: 1524
- Pages with candidates: 509

Safety contract:

- embedding candidates are not source truth
- embedding candidates cannot answer directly
- embedding candidates cannot prove claims
- retrieval must verify against source OCR/table/visual/source-trace evidence


## Qdrant loader compatibility fix

This version emits the legacy quality/manifest aliases expected by
`trace_net_qdrant_loader_v1`:

- `trace_net_embedding_candidates_v1_quality.json`
- `trace_net_embedding_candidates_v1_manifest.json`

It also maps OCR page text candidates into the loader-safe `context_helper`
bucket while preserving `candidate_type: ocr_page_text`, and every candidate now
carries a non-empty `traceability` object plus source-resolution and authority
gate flags.
