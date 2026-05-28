# OCR coverage pipeline/quality integration

This patch makes OCR coverage an official backend health signal.

## What changes

- Adds `ocr_coverage_audit` to the normal backend pipeline after `source_link_audit` and before `rag_eval`.
- Adds `ocr_coverage_summary` to the pipeline manifest/status output.
- Adds OCR coverage checks to `check_pipeline_quality.py`.
- Keeps empty OCR files as a visible warning by default, because some pages may be blank/separator/image-only pages.
- Adds `--require-complete-ocr-text` for later strict mode after the empty OCR pages are reviewed.

## Normal command

```bash
python scripts/run_tiff_backend_pipeline.py --config local_config.yaml
python scripts/check_pipeline_quality.py --require-incremental-smoke
python scripts/show_pipeline_status.py
```

Expected local-MVP behavior for the current sample:

```text
ocr_local_paths_ready: True
ocr_empty_files: 14
quality gate: OK
```

## Strict future command

Only use this after blank/separator pages are reviewed or OCR is regenerated where needed:

```bash
python scripts/check_pipeline_quality.py --require-complete-ocr-text
```

That command should fail while the current 14 empty OCR files remain.
