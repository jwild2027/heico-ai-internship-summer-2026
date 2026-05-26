# TIFF SQLite persistence

The TIFF upload scanner can now save every scan report to SQLite in addition to
writing a JSON file.

## Streamlit

```bash
python -m streamlit run tiff_upload_scan.py
```

Keep **Save scan report to SQLite** checked. The default database path is:

```text
local_data/tiff_scans.db
```

The app saves:

- uploaded TIFF under `local_data/uploads/`
- JSON report under `local_data/json_scans/`
- normalized metadata into SQLite

## CLI

```bash
python scripts/scan_tiff_to_json.py \
  --input "/c/Users/juswil/Desktop/00000018.tif" \
  --output "local_data/json_scans/00000018.scan.json" \
  --ocr \
  --tesseract-cmd 'C:\Users\juswil\AppData\Local\Programs\Tesseract-OCR\tesseract.exe' \
  --db-path "local_data/tiff_scans.db" \
  --print
```

## Tables

Core inventory tables:

```text
tiff_files
tiff_technical_metadata
tiff_drawing_metadata
tiff_ocr_texts
```

New document/report tables:

```text
tiff_manual_metadata
tiff_document_classification
tiff_scan_reports
```

The current implementation stores one latest scan report per file. Re-scanning a
file updates its normalized metadata and replaces the OCR-region rows for that
file.

## Quick DB check

```bash
python - <<'PY'
from tiff.sqlite_store import connect, list_tiff_files
with connect('local_data/tiff_scans.db') as conn:
    for row in list_tiff_files(conn, limit=10):
        print(row)
PY
```
