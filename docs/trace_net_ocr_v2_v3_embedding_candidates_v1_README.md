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
