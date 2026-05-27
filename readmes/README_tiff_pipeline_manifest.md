# TIFF Backend Pipeline Manifest

This patch adds an audit manifest for the backend pipeline.

Every backend run can now write:

```text
local_data/pipeline_runs/latest_backend_pipeline.json
local_data/pipeline_runs/tiff_backend_pipeline_<run_id>.json
```

The manifest records:

```text
pipeline status
step return codes
step elapsed seconds
SQLite table counts
RAG eval summary
part catalog QA summary
important artifact paths
```

## Install

```bash
unzip -o ~/Downloads/heico_tiff_pipeline_manifest_files.zip -d .
```

## Test

```bash
python -m pytest tests/unit/test_tiff_pipeline_manifest.py tests/unit/test_tiff_pipeline_runner.py -q
```

## Run backend pipeline and write manifest

```bash
python scripts/run_tiff_backend_pipeline.py --config local_config.yaml
```

## Show latest status

```bash
python scripts/show_pipeline_status.py
```

## Dry run manifest

```bash
python scripts/run_tiff_backend_pipeline.py --config local_config.yaml --dry-run
```

## Skip manifest

```bash
python scripts/run_tiff_backend_pipeline.py --config local_config.yaml --skip-manifest
```
