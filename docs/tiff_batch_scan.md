# Batch TIFF scan

This adds a folder-level scanner for raw TIFF files. It is intended for local-only test folders such as:

```text
local_data/sample_tiffs
```

It creates:

```text
local_data/json_scans/<relative_path>.tif.scan.json
local_data/json_scans/batch_summary.json
local_data/db/tiff_scans.db
```

## Run on the local sample folder

```bash
python scripts/batch_scan_tiffs_to_json.py \
  --input-dir local_data/sample_tiffs \
  --output-dir local_data/json_scans \
  --db-path local_data/db/tiff_scans.db \
  --ocr \
  --tesseract-cmd 'C:\Users\juswil\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'
```

For a quick dry run on five files:

```bash
python scripts/batch_scan_tiffs_to_json.py \
  --input-dir local_data/sample_tiffs \
  --output-dir local_data/json_scans \
  --db-path local_data/db/tiff_scans.db \
  --ocr \
  --tesseract-cmd 'C:\Users\juswil\AppData\Local\Programs\Tesseract-OCR\tesseract.exe' \
  --limit 5
```

For a faster inventory-only pass without OCR and without hashing:

```bash
python scripts/batch_scan_tiffs_to_json.py \
  --input-dir local_data/sample_tiffs \
  --output-dir local_data/json_scans \
  --db-path local_data/db/tiff_scans.db \
  --no-hash
```

## Inspect saved rows

Simple summary:

```bash
python scripts/summarize_tiff_db.py --db-path local_data/db/tiff_scans.db
```

Raw Python inspection:

```bash
python - <<'PY'
from tiff.sqlite_store import connect, list_tiff_files

with connect('local_data/db/tiff_scans.db') as conn:
    rows = list_tiff_files(conn, limit=20)

for row in rows:
    print(row)
PY
```

## Notes

- The script preserves subfolder structure under the JSON output directory.
- Existing JSON files are overwritten by default. Use `--no-overwrite` to skip them.
- Failures are written as `.scan.json` failure reports unless `--stop-on-error` is used.
- Keep `local_data/` ignored by Git.
