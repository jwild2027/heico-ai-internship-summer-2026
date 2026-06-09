# Production Storage Migration Draft

## Goal

Move from the local MVP shape:

```text
Streamlit UI -> FastAPI -> service layer -> storage adapters -> local JSON/SQLite artifacts
```

to the production shape:

```text
Streamlit UI -> FastAPI -> service layer -> storage adapters -> PostgreSQL / OpenSearch / Qdrant / ResCarta
```

The API contract should remain stable while the adapter implementations change.

## Storage responsibilities

### PostgreSQL

PostgreSQL is the system of record for structured data and graph relationships:

- documents
- pages
- ATA sections
- source files
- source links
- OCR records
- parts
- nomenclature
- part mentions
- page contexts
- RAG chunk metadata
- feedback
- QA findings
- file state
- pipeline/quality snapshots

PostgreSQL should not store TIFF bytes or dense vector arrays.

### OpenSearch

OpenSearch is the keyword and full-text retrieval layer:

- OCR page text
- RAG chunk text
- page context summaries
- part/nomenclature search documents

OpenSearch stores denormalized searchable documents. PostgreSQL remains the truth source.

### Qdrant

Qdrant stores dense embeddings and small payloads:

- chunk embeddings
- page-context embeddings
- future optional image/page embeddings

Payloads must include `chunk_id` and/or `page_id` so the backend can resolve the result through PostgreSQL graph relationships.

### ResCarta / file storage

ResCarta or file storage remains the source of raw TIFFs and source viewing links. The derived databases store IDs, paths, URIs, hashes, and metadata only.

## Critical traceability invariant

Every answer should be able to trace back:

```text
answer -> answer_sources -> rag_chunk/page/part -> page -> document/ATA -> source_link -> TIFF/OCR source
```

Every Qdrant result must be resolvable:

```text
qdrant point -> chunk_id/page_id -> PostgreSQL graph -> source link/context
```

## Migration phases

1. Keep local adapters as the reference implementation.
2. Add PostgreSQL schema and read-only migration writer for the 509-page sample.
3. Add PostgreSQL-backed `CatalogStore`, `TraceStore`, `FeedbackStore`, and `QualityStore`.
4. Add OpenSearch indexing for OCR pages/chunks/context.
5. Add Qdrant indexing for chunk/context embeddings.
6. Run API contract tests against production adapters.
7. Compare local adapter results and production adapter results on the 509-page sample.
8. Only then pilot on a real server batch.

## Pre-server guardrails

- Do not OCR the full server on first access.
- Do not embed the full server on first access.
- Do not generate AI page context for every page at production scale without a selective/on-demand strategy.
- Start with inventory, OCR-depth audit, source traceability, and a small pilot batch.
