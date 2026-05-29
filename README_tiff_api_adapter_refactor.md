# TIFF API Adapter Refactor

This patch routes the FastAPI boundary through the storage adapter layer while keeping the public API routes the same.

## What changed

```text
Streamlit UI
  -> FastAPI routes
  -> tiff.api_adapter_services.TiffApiServices
  -> storage adapters
  -> local artifacts now
  -> PostgreSQL/OpenSearch/Qdrant/ResCarta later
```

## Updated files

```text
apps/api/tiff_api.py
scripts/check_tiff_api_ready.py
tiff/api_adapter_services.py
tiff/storage_adapters.py
tests/unit/test_tiff_api_adapter_services.py
```

## Run

```bash
python -m pytest tests/unit/test_tiff_storage_adapters.py tests/unit/test_tiff_api_adapter_services.py -q
python scripts/check_tiff_api_ready.py --write-json
python scripts/check_tiff_storage_adapters.py --write-json
python scripts/check_api_adapter_quality.py --write-json
python scripts/refresh_api_adapter_quality_summary.py
```

Then run the full quality wrapper:

```bash
python scripts/check_full_system_quality.py \
  --require-api-adapter-quality \
  --require-incremental-smoke \
  --require-user-query-tests \
  --require-realistic-query-trace \
  --require-slow-realistic-query-trace \
  --require-source-package-traceability
```

## Start API

```bash
python -m uvicorn apps.api.tiff_api:app --reload --host 127.0.0.1 --port 8000
```

Routes remain unchanged:

```text
GET  /status
GET  /organization/summary
GET  /organization/parts/{part_number}
GET  /organization/pages/{page_id}
GET  /organization/ata/{ata_code}
GET  /trace/part/{part_number}
GET  /trace/page/{page_id}
GET  /trace/vector
POST /ask
POST /feedback
GET  /feedback/summary
```
