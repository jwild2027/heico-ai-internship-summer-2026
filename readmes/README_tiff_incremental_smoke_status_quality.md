# Changed-page incremental smoke + status/quality integration

This patch covers the next two backend hardening steps:

1. Run a controlled changed-page incremental smoke test.
2. Wire the smoke-test result into the pipeline manifest, status output, and quality gate.

## What it adds

- `scripts/smoke_test_incremental_changed_page.py`
- `tiff/incremental_changed_page_smoke.py`
- hardened `scripts/update_changed_page_backend.py`
- incremental smoke summary support in `tiff/pipeline_manifest.py`
- incremental smoke checks in `tiff/pipeline_quality.py`
- `--require-incremental-smoke` in `scripts/check_pipeline_quality.py`

## Normal command

```bash
python scripts/smoke_test_incremental_changed_page.py --config local_config.yaml --write-json
python scripts/check_pipeline_quality.py --require-incremental-smoke
python scripts/show_pipeline_status.py
```

Expected behavior:

- exactly one temporary TIFF is changed
- OCR is skipped for the smoke test
- changed-page backend path is used
- full backend rebuild is not used
- state commits only after successful downstream work
- latest pipeline manifest shows an Incremental smoke summary
- quality gate reports incremental smoke checks

The test uses `local_data/incremental_smoke/` and does not mutate the real sample TIFF tree.
