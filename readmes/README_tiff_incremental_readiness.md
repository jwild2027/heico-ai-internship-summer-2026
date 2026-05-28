# TIFF incremental readiness audit

This patch starts the incremental hardening step without changing processing logic.

It adds a read-only command-line audit:

```bash
python scripts/audit_incremental_readiness.py --config local_config.yaml
```

The audit checks:

- TIFF root, search DB, ResCarta export dir, and eval questions exist.
- Changed-page backend files are present.
- A synthetic changed TIFF plans `scripts/update_changed_page_backend.py` instead of a full rebuild.
- Safe-commit rules still prevent state commits on dry-run/skipped/failed downstream work.
- The latest backend quality gate and manifest are OK.
- The current incremental state DB can be previewed without writing state or changed-list files.

It prints to the terminal and writes no files by default. Optional JSON:

```bash
python scripts/audit_incremental_readiness.py --config local_config.yaml --write-json
```

The real incremental run is still:

```bash
python scripts/run_incremental_tiff_pipeline.py --config local_config.yaml --backend-mode changed-pages
```

## Fix in this patch

The readiness audit now accepts the quality gate status value `ok` as well as
`OK`. It also reads both current and older source-link readiness field names
from `latest_backend_pipeline.json`, including:

```text
ready_for_local_source_review
ready_for_real_rescarta_deeplinks
```

This prevents a healthy backend from being marked `NEEDS ATTENTION` just because
status capitalization or source-link field names differ between patches.
