# API contract in-process compatibility fix

This patch restores `DEFAULT_OUTPUT` and rewrites the API contract runner so quality-gate runs can use `--in-process` without requiring uvicorn to be running.

Recommended quality flow:

```bash
python scripts/run_api_contract_tests.py --in-process --write-json
python scripts/check_api_contract_quality.py --write-json
python scripts/refresh_api_contract_quality_summary.py
```

Use live HTTP only when uvicorn is already running:

```bash
python -m uvicorn apps.api.tiff_api:app --reload --host 127.0.0.1 --port 8000
python scripts/run_api_contract_tests.py --base-url http://127.0.0.1:8000 --write-json
```
