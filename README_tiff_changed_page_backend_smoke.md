# Changed-page backend smoke test

This adds a small smoke-test script for Goal 1.

It touches one TIFF timestamp so stat-based incremental detection sees exactly one changed file, then runs:

```bash
python scripts/run_incremental_tiff_pipeline.py --config local_config.yaml --backend-mode changed-pages
```

It verifies:

- `Changed list count: 1`
- OCR changed TIFF step succeeds
- changed-page backend step succeeds
- state commits only after success
- a follow-up dry run sees `Changed list count: 0`

The script changes only file timestamps, not TIFF contents.

Run:

```bash
python scripts/smoke_test_changed_page_backend_mode.py --config local_config.yaml
```

Preview without touching/running:

```bash
python scripts/smoke_test_changed_page_backend_mode.py --config local_config.yaml --no-run
```
