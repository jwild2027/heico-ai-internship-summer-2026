# TRACE-Net E2E Dynamic Query Endpoint Reranker v2

This patch tightens the dynamic query endpoint ranking behavior while keeping the same safety contract.

## Changes

- Boosts exact matches in the field that matches query intent.
- Suppresses generic table/OCR tokens such as `NUMBER` for part-number/manual-reference queries.
- Keeps exact part-number values above generic text hits.
- Normalizes small OCR spacing issues such as `MAINTENANCEMANUAL WITH` to `MAINTENANCE MANUAL WITH` before citations are shown.
- Does not rerun OCR, page classification, embeddings, summaries, graph construction, or source ingest.
- Does not mutate source truth or write to Postgres, Qdrant, or OpenSearch.

## Safety contract

Dynamic v2 remains retrieval/gate constrained. It can surface citation/source-trace-ready evidence for review, but it does not grant direct answer authority or proof authority.
