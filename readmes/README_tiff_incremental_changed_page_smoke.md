# TIFF incremental changed-page smoke test

This patch hardens the changed-page incremental path and adds a controlled smoke test.

## Why

The backend already has:

- full pipeline quality gate
- QA severity triage
- expanded RAG evals
- source-link audit
- incremental readiness audit

The next risk is the changed-page incremental path. It should update only affected pages and should never commit incremental state if a changed TIFF cannot be matched to an indexed page.

## What changed

### `scripts/update_changed_page_backend.py`

The changed-page backend update now:

- fails by default if a non-empty changed list has unmatched TIFF paths
- runs QA triage after raw QA
- runs source-link audit after page-scoped updates
- still runs embedding refresh and RAG eval
- keeps command-line output only

New optional flags:

```bash
--allow-unmatched
--skip-triage
--skip-source-audit
--source-audit-json local_data/source_links/source_link_audit.json
--triage-limit 12
```

Use `--allow-unmatched` only for diagnostics. Normal incremental runs should fail on unmatched changed paths so state is not committed prematurely.

### `scripts/smoke_test_incremental_changed_page.py`

This script performs a controlled smoke test without touching the real `local_data/sample_tiffs` tree:

1. selects one source-linked page from `local_data/db/tiff_search.db`
2. copies its TIFF into `local_data/incremental_smoke/sample_tiffs`
3. seeds a temporary incremental state DB
4. mutates the temporary TIFF copy
5. runs the safe incremental pipeline in `changed-pages` mode with OCR skipped
6. verifies that the changed-page backend path was used instead of the full rebuild path

Run:

```bash
python scripts/smoke_test_incremental_changed_page.py --config local_config.yaml --write-json
python scripts/check_pipeline_quality.py
python scripts/show_pipeline_status.py
```

Expected successful shape:

```text
Changed-page incremental smoke test
  Status: OK
  Changed list count: 1
  OCR skipped: True
  Changed-page backend planned: True
  Used changed-page update script: True
  Used full backend rebuild: False
  State committed: True
```

The smoke test may take around the same amount of time as one RAG eval run because the changed-page backend still runs the expanded eval set after updating page-scoped rows.
