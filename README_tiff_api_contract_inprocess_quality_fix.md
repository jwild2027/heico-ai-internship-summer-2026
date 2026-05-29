# API contract in-process/default quality fix

This patch makes `scripts/run_api_contract_tests.py` default to FastAPI TestClient
in-process mode when `--base-url` is not provided, so Uvicorn does not need to be
running for quality-gate runs.

It also updates `scripts/check_full_system_quality.py` so extra quality reports
that store checks as `{status: ok}` display as OK, not false FAIL labels.

## Commands

```bash
python scripts/run_api_contract_tests.py --in-process --write-json
python scripts/check_api_contract_quality.py --write-json
python scripts/refresh_api_contract_quality_summary.py
python scripts/check_full_system_quality.py \
  --require-api-adapter-quality \
  --require-api-contract-tests \
  --require-incremental-smoke \
  --require-user-query-tests \
  --require-realistic-query-trace \
  --require-slow-realistic-query-trace \
  --require-source-package-traceability
```

To test a live server intentionally:

```bash
python scripts/run_api_contract_tests.py --base-url http://127.0.0.1:8000 --write-json
```
