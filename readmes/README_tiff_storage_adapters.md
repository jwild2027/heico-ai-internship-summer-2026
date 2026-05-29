# TIFF Storage Adapter Skeletons

This patch adds the first production-storage boundary for the TIFF/RAG system.
It does **not** migrate data to PostgreSQL/OpenSearch/Qdrant yet. Instead, it
creates stable interfaces and local implementations so the FastAPI/UI layer can
use one shape now and later swap the backing store.

## Why this exists

Current local MVP:

```text
FastAPI / Streamlit
  -> local JSON graph/export files
  -> SQLite/local scripts
  -> JSONL feedback
```

Future production:

```text
FastAPI / Streamlit
  -> PostgreSQL catalog + graph
  -> OpenSearch keyword/OCR search
  -> Qdrant vector search
  -> ResCarta/source-link store
  -> PostgreSQL feedback tables
```

The adapter layer keeps the API and UI stable while the implementation changes.

## New files

```text
tiff/storage_adapters.py
scripts/check_storage_adapters_ready.py
tests/unit/test_tiff_storage_adapters.py
```

## Interfaces added

```text
CatalogStore
  documents/pages/parts/ATA/source metadata

SourceStore
  page -> source link / TIFF / OCR

VectorStore
  future Qdrant payload -> graph/page trace

KeywordSearchStore
  future OpenSearch keyword/OCR search

FeedbackStore
  thumbs up/down/comments

QualityStore
  pipeline/graph quality summaries
```

## Current implementations

```text
LocalJsonCatalogStore
  reads local_data/organization/export/*.json

LocalGraphTraceStore
  reads local_data/organization/graph/graph_nodes.json and graph_edges.json

LocalFeedbackStore
  writes local_data/feedback/user_feedback.jsonl

LocalQualityStore
  reads local_data/pipeline_runs/latest_quality_gate.json and graph_quality.json

NullKeywordSearchStore
  placeholder for OpenSearch

NullVectorStore
  placeholder for Qdrant, with graph trace simulation when page_id is known
```

## Run

```bash
python -m pytest tests/unit/test_tiff_storage_adapters.py -q
python scripts/check_storage_adapters_ready.py --write-json
```

Output:

```text
local_data/api/storage_adapters_ready.json
```

## Next integration step

Wire the FastAPI endpoints through the adapter bundle:

```text
/api route
  -> adapter interface
  -> local implementation now
  -> PostgreSQL/OpenSearch/Qdrant implementation later
```
