# TIFF API / Storage Adapter Quality Gate

This patch adds a read-only quality layer for the FastAPI boundary and storage adapter seam.

It reads:

- `local_data/api/tiff_api_ready.json`
- `local_data/api/storage_adapter_ready.json`
- optional `local_data/feedback/user_feedback_summary.json`

and writes:

- `local_data/api/api_adapter_quality.json`

Run:

```bash
python -m pytest tests/unit/test_tiff_api_adapter_quality.py -q
python scripts/check_tiff_api_ready.py --write-json
python scripts/check_tiff_storage_adapters.py --write-json
python scripts/check_api_adapter_quality.py --write-json
python scripts/refresh_api_adapter_quality_summary.py
```

Then run your main quality gate as usual.

The summary is attached to `latest_backend_pipeline.json` under `api_adapter_quality` so the pipeline manifest carries API/adapter readiness alongside graph, source-package, OCR, and realistic query trace quality.
