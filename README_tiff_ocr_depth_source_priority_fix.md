# OCR depth audit source-priority fix

This patch fixes the OCR-depth audit so explicit inputs win over the default local SQLite DB.

The failed unit test created a temporary `export/page_index.json`, but `run_ocr_depth_audit()` fell back to
`local_data/db/tiff_search.db`, so it saw 509 real pages instead of the 4 fake test pages.

Run:

```bash
python -m pytest tests/unit/test_tiff_ocr_depth_audit.py -q
python scripts/audit_ocr_depth.py --config local_config.yaml --write-json
python scripts/audit_ocr_depth.py --zip /c/Users/juswil/Documents/00000027/metadata.zip --write-json --json-output local_data/ocr/ocr_depth_zip_audit.json
```
