# Page image-recognition role extraction fix

Fixes `audit_page_image_recognition.py` showing `Page roles: unknown: 509` when page-context records use `page_role`, `classification`, or `primary_role` instead of only `role`.

Run:

```bash
python scripts/apply_page_image_role_fix.py
python -m pytest tests/unit/test_tiff_page_image_recognition.py tests/unit/test_tiff_page_image_role_fix.py -q
python scripts/audit_page_image_recognition.py --write-json --write-graph-overlay
```
