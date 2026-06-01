# TIFF server-access checklist and runbook

This patch adds a read-only planning artifact for the first time the real TIFF/ResCarta server is available.

It does not scan the server or mutate local data. It writes a checklist and command runbook that should be reviewed before any large-scale OCR, indexing, graph, OpenSearch, Qdrant, or PostgreSQL work.

## Commands

```bash
python -m pytest tests/unit/test_tiff_server_access_runbook.py -q
python scripts/prepare_server_access_runbook.py --write
```

Optional with a known server root placeholder:

```bash
python scripts/prepare_server_access_runbook.py \
  --server-root /path/to/server/root \
  --target-total-tb 5 \
  --max-files 100000 \
  --pilot-pages 500 \
  --write
```

Outputs:

```text
local_data/batch_audit/server_access_checklist.json
local_data/batch_audit/server_access_runbook.md
```

## Purpose

The generated runbook prepares the first-access flow:

1. Confirm read-only access.
2. Run a capped inventory sample.
3. Run OCR-depth audit.
4. Run document batch shape audit.
5. Run a small OCR pilot only after approval.
6. Run quality gates before scaling.

The guardrail is: never run OCR, embeddings, or AI page-context generation across the full server on first access.
