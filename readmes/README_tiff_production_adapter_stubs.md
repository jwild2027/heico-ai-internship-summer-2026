# TIFF Production Adapter Stubs

This patch adds future production storage adapter stubs for:

- PostgreSQL catalog/graph/feedback/quality stores
- OpenSearch keyword/full-text search store
- Qdrant vector search store
- ResCarta/source-link resolver

The classes are intentionally safe before production services exist. They do not connect to services yet. Their methods raise `ProductionAdapterNotConfigured` with a clear message.

## Check readiness

```bash
python -m pytest tests/unit/test_tiff_production_adapter_stubs.py -q
python scripts/check_production_adapter_stubs.py --write-json
```

Output:

```text
local_data/api/production_adapter_stubs_ready.json
```

Before server/service access, unconfigured production services are expected. The readiness check mainly verifies that production schema drafts exist.

After production services exist, run:

```bash
python scripts/check_production_adapter_stubs.py --require-configured --write-json
```

## Environment variables reserved for production

```text
HEICO_POSTGRES_DSN
HEICO_OPENSEARCH_URL
HEICO_QDRANT_URL
HEICO_RESCARTA_BASE_URL
```

## Target architecture

```text
Streamlit UI
  -> FastAPI
  -> service layer
  -> storage adapter interface
  -> local artifacts today
  -> PostgreSQL / OpenSearch / Qdrant / ResCarta later
```
