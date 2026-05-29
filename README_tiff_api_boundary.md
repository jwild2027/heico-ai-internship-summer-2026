# TIFF API Boundary Starter

This patch adds the first production-oriented API boundary for the TIFF/RAG MVP.

It does **not** migrate storage yet.  It wraps the current local artifacts behind a stable interface so later we can replace JSON/SQLite/local scripts with PostgreSQL, OpenSearch, and Qdrant behind the same API contract.

## Added files

```text
tiff/api_backend.py
apps/api/tiff_api.py
scripts/check_tiff_api_ready.py
tests/unit/test_tiff_api_backend.py
README_tiff_api_boundary.md
```

## Install dependency if needed

FastAPI/uvicorn may already be installed.  If not:

```bash
python -m pip install fastapi uvicorn
```

## Run tests

```bash
python -m pytest tests/unit/test_tiff_api_backend.py -q
```

## Check local API readiness without starting the server

```bash
python scripts/check_tiff_api_ready.py --write-json
```

Expected shape:

```text
TIFF API readiness
  Status: OK
  Backend quality: OK
  Graph nodes: 3788
  Page contexts: 509
  Source links: 509
```

## Start the API

```bash
python -m uvicorn apps.api.tiff_api:app --reload --host 127.0.0.1 --port 8000
```

Then open:

```text
http://127.0.0.1:8000/docs
```

## Initial endpoints

```text
GET  /status
GET  /organization/summary
GET  /organization/parts/{part_number}
GET  /organization/pages/{page_id}
GET  /organization/ata/{ata_code}
GET  /trace/part/{part_number}
GET  /trace/page/{page_id}
GET  /trace/vector?page_id=...&chunk_id=...&score=...
POST /ask
POST /feedback
GET  /feedback/summary
```

## Why this matters

Current local backend:

```text
JSON graph/export files
SQLite search DB
local script entrypoints
local page context files
```

Future production backend:

```text
PostgreSQL graph/catalog
OpenSearch OCR/keyword search
Qdrant vector retrieval
FastAPI service
UI calls API instead of local scripts/files
```

The API boundary lets us start building the UI against stable routes now.
