# TIFF Incremental Backend Pipeline

This patch adds the first true incremental wrapper for the local TIFF/RAG backend.

The current backend wrapper rebuilds everything from the ResCarta staging export.
This incremental wrapper adds the missing front-end behavior:

1. scan the TIFF source root
2. detect new/changed/unchanged/missing TIFF files
3. write `local_data/changed_tiffs.txt`
4. optionally OCR only the changed files
5. optionally run the backend search/catalog/RAG/QA/eval pipeline

## Files added

```text
tiff/incremental_state.py
tiff/incremental_pipeline.py
scripts/run_incremental_tiff_pipeline.py
tests/unit/test_tiff_incremental_state.py
tests/unit/test_tiff_incremental_pipeline.py
README_tiff_incremental_backend_pipeline.md
```

## Main command

```bash
python scripts/run_incremental_tiff_pipeline.py --config local_config.yaml --run-backend-when-unchanged
```

On the first run, every TIFF under the configured root is considered new. On the
second run, unchanged TIFF files should produce:

```text
Changed list count: 0
ocr_changed_tiffs: SKIPPED
backend_pipeline: SKIPPED
```

unless `--run-backend-when-unchanged` is provided.

## Useful dry run

```bash
python scripts/run_incremental_tiff_pipeline.py --config local_config.yaml --dry-run
```

This writes the changed list and prints the planned commands without running OCR
or the backend rebuild.

## Config keys

Add any of these to `local_config.yaml` if needed:

```yaml
tiff_root: local_data/sample_tiffs
incremental_state_db: local_data/db/tiff_incremental_state.db
changed_tiffs_path: local_data/changed_tiffs.txt
scan_db_path: local_data/db/tiff_scans_full.db
json_scan_dir: local_data/json_scans_incremental
rescarta_export_dir: local_data/rescarta_exports
db_path: local_data/db/tiff_search.db
embed_model: bge-m3:latest
tesseract_cmd: C:\Users\juswil\AppData\Local\Programs\Tesseract-OCR\tesseract.exe
incremental_hash_mode: stat
```

`incremental_hash_mode` can be:

```text
stat    fast; uses file size + modified time
sha256  slower; hashes TIFF file bytes
```

For a very large server, `stat` is faster for frequent runs. Use `sha256` when
you need stronger verification.

## Common runs

Create changed list only:

```bash
python scripts/run_incremental_tiff_pipeline.py --config local_config.yaml --skip-ocr --skip-backend
```

Run OCR only when files changed:

```bash
python scripts/run_incremental_tiff_pipeline.py --config local_config.yaml --skip-backend
```

Run backend even when nothing changed:

```bash
python scripts/run_incremental_tiff_pipeline.py --config local_config.yaml --run-backend-when-unchanged
```

Reset embeddings during backend stage:

```bash
python scripts/run_incremental_tiff_pipeline.py --config local_config.yaml --reset-embeddings
```

## Why this matters

This is the bridge from the current pilot rebuild workflow to a future 5 TB
workflow. The full production version should eventually update OCR, search,
RAG chunks, and embeddings only for changed pages.
