# TIFF Production Schema Drafts

This patch adds versioned schema drafts for the future production storage layer.

It does **not** connect to PostgreSQL, OpenSearch, or Qdrant. It only writes reviewable artifacts so the team can agree on the target storage shape before server access and before migration work.

## Files added

```text
tiff/production_schema.py
scripts/write_production_schema_drafts.py
tests/unit/test_tiff_production_schema.py
README_tiff_production_schema_drafts.md
```

## Run

```bash
python -m pytest tests/unit/test_tiff_production_schema.py -q
python scripts/write_production_schema_drafts.py
```

Outputs:

```text
local_data/architecture/production_schema/postgres_schema.sql
local_data/architecture/production_schema/opensearch_mappings.json
local_data/architecture/production_schema/qdrant_collections.json
local_data/architecture/production_schema/storage_migration_plan.md
local_data/architecture/production_schema/production_schema_summary.json
```

Validate existing outputs:

```bash
python scripts/write_production_schema_drafts.py --validate-only
```

## Storage responsibilities

### PostgreSQL

System of record for structured data and graph relationships:

```text
documents
pages
ATA sections
source links
OCR records
parts
nomenclature
part mentions
page contexts
RAG chunk metadata
feedback
QA findings
file state
pipeline quality
```

PostgreSQL should not store TIFF bytes or dense vector arrays.

### OpenSearch

Keyword/full-text search for:

```text
OCR page text
RAG chunk text
AI page context summaries
part/nomenclature search documents
```

### Qdrant

Dense vector search for:

```text
RAG chunks
page context summaries
future optional image/page embeddings
```

Every Qdrant payload must include at least:

```text
chunk_id and/or page_id
```

so the backend can resolve the vector result through the PostgreSQL graph.

### ResCarta / file storage

Raw TIFFs and source viewing remain in ResCarta/file storage. The derived stores keep source IDs, paths, URLs, hashes, and quality state.

## Traceability invariant

Every answer should trace back:

```text
answer
  -> source/chunk/page/part
  -> page
  -> document
  -> ATA
  -> source link
  -> TIFF/OCR source
```

Every Qdrant result should trace back:

```text
Qdrant point
  -> chunk_id/page_id
  -> PostgreSQL graph
  -> source link/context
```
