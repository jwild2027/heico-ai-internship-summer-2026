# API Contract Quality Gate

Adds API contract results to the full system quality wrapper.

## Commands

Run API contract tests:

```bash
python scripts/run_api_contract_tests.py --write-json
```

Check and refresh quality:

```bash
python scripts/check_api_contract_quality.py --write-json
python scripts/refresh_api_contract_quality_summary.py
```

Full system quality:

```bash
python scripts/check_full_system_quality.py \
  --require-api-adapter-quality \
  --require-api-contract-tests \
  --require-incremental-smoke \
  --require-user-query-tests \
  --require-realistic-query-trace \
  --require-slow-realistic-query-trace \
  --require-source-package-traceability
```
