# OCR Depth Audit Source Selection Fix

Fixes `run_ocr_depth_audit(export_dir=...)` so explicit non-default export directories are honored before falling back to the configured SQLite DB. This keeps temporary test exports and ad-hoc page-index audits isolated from the real local backend DB.

Run:

```bash
python -m pytest tests/unit/test_tiff_ocr_depth_audit.py -q
python scripts/audit_ocr_depth.py --config local_config.yaml --write-json
python scripts/audit_ocr_depth.py --zip /c/Users/juswil/Documents/00000027/metadata.zip --write-json --json-output local_data/ocr/ocr_depth_zip_audit.json
```
