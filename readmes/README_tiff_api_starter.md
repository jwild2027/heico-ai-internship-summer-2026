# TIFF/RAG API starter

This patch adds a small read-only API layer over the local TIFF backend artifacts.

It intentionally reads the stable outputs that already pass the quality gate:

- `local_data/organization/export/*.json`
- `local_data/pipeline_runs/latest_backend_pipeline.json`
- `local_data/pipeline_runs/latest_quality_gate.json`
- `scripts/ask_tiff_rag.py` for the `/ask` endpoint

It does not rebuild OCR, update the SQLite database, move TIFF files, or modify source files.

## Check readiness

```bash
python scripts/check_tiff_api_ready.py --strict
```

## Run tests

```bash
python -m pytest tests/unit/test_tiff_api_backend.py -q
```

## Install API dependencies

```bash
python -m pip install fastapi uvicorn
```

## Run the API

```bash
python -m uvicorn apps.api.tiff_api:app --reload
```

Then open:

```text
http://127.0.0.1:8000/docs
```

## Initial endpoints

```text
GET  /health
GET  /status
GET  /organization/summary
GET  /organization/part/{part_number}
GET  /organization/ata/{ata_code}
GET  /organization/page/{page_id}
POST /ask
```

Example:

```bash
curl http://127.0.0.1:8000/organization/part/120-37313-001
```

The `/ask` endpoint calls the existing CLI path and can be slower for broad LLM questions.
