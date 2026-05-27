# Incremental pipeline safe-commit and smoke-test patch

This patch makes the incremental TIFF pipeline safer for production use.

## What changed

The pipeline now separates:

1. detecting changed TIFFs
2. writing `changed_tiffs.txt`
3. running OCR/backend commands
4. committing the incremental state DB

The state DB is committed only after downstream processing succeeds. This prevents a failed OCR/backend run from accidentally marking changed files as already processed.

## Important behavior

Dry run:

```bash
python scripts/run_incremental_tiff_pipeline.py --config local_config.yaml --dry-run
```

- writes `changed_tiffs.txt` for inspection
- does not run commands
- does not update the state DB

Real run:

```bash
python scripts/run_incremental_tiff_pipeline.py --config local_config.yaml
```

- detects changed TIFFs
- runs OCR only when there are changed TIFFs
- runs the backend only when there are changed TIFFs unless `--run-backend-when-unchanged` is used
- commits the state DB only after processing succeeds

## Smoke test

Run an isolated change-detection smoke test without touching your real sample folder:

```bash
python scripts/smoke_test_incremental_change_detection.py --config local_config.yaml --limit 5
```

Expected:

```text
Baseline new files: 5
Second-run changed list count: 0
After adding one TIFF changed list count: 1
Smoke test PASSED
```

## Useful commands

Reset incremental state:

```bash
python scripts/run_incremental_tiff_pipeline.py --config local_config.yaml --reset-state --dry-run
```

Force backend even when no TIFFs changed:

```bash
python scripts/run_incremental_tiff_pipeline.py --config local_config.yaml --run-backend-when-unchanged
```
