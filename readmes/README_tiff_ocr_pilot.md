# TIFF OCR Pilot

This patch adds a safe, isolated OCR pilot before any production OCR baseline.
It writes only to `local_data/ocr/pilot` by default and does not modify the main
SQLite database, graph, RAG chunks, source links, or OCR export.

## Why this exists

If a real TIFF server has only header OCR or no body OCR, OpenSearch, Qdrant,
RAG, and graph extraction need a full-page OCR layer first. The pilot checks a
small batch before committing to a large OCR job.

## Run unit tests

```bash
python -m pytest tests/unit/test_tiff_ocr_pilot.py -q
```

## Pilot against the raw 509-page ZIP

This uses Tesseract if available. If Tesseract is not installed, it reports that
an OCR engine is missing instead of changing production data.

```bash
python scripts/run_ocr_pilot.py \
  --zip /c/Users/juswil/Documents/00000027/metadata.zip \
  --limit 10 \
  --engine auto \
  --write-json
```

Then audit the generated pilot OCR:

```bash
python scripts/audit_ocr_depth.py \
  --export-dir local_data/ocr/pilot \
  --write-json \
  --json-output local_data/ocr/ocr_pilot_depth_audit.json
```

## Pilot against the current processed export

This does not run OCR. It copies existing OCR from `page_index.json` into the
pilot folder so the pilot/report path can be tested end to end.

```bash
python scripts/run_ocr_pilot.py \
  --export-dir local_data/organization/export \
  --limit 10 \
  --engine existing \
  --write-json
```

## Pilot against a future server folder

```bash
python scripts/run_ocr_pilot.py \
  --root /path/to/tiff/server/root \
  --limit 100 \
  --engine auto \
  --write-json
```

## Outputs

```text
local_data/ocr/pilot/pages/                  copied/extracted TIFF sample
local_data/ocr/pilot/ocr/                    OCR text output
local_data/ocr/pilot/page_index.json         pilot page index for OCR-depth audit
local_data/ocr/pilot/reports/ocr_pilot_manifest.json
local_data/ocr/pilot/reports/ocr_pilot_report.json
```

## Notes

- `--engine auto` uses `tesseract` if the CLI is on PATH; otherwise it tries to
  use existing OCR when available.
- `--engine existing` copies OCR already referenced by the organization export.
- `--engine none` is useful for dry/safety tests and should return `NEEDS ATTENTION`.
- Use `--force` only when you want to regenerate existing pilot OCR outputs.
