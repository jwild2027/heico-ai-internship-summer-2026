# Page image-recognition quality public API fix

Restores `build_page_image_recognition_quality_report` and `summarize_page_image_recognition_audit` with a parser compatible with the current audit JSON shape.

Run:

```bash
python scripts/apply_page_image_quality_public_api_fix.py
python -m pytest tests/unit/test_tiff_page_image_recognition_quality.py tests/unit/test_tiff_page_image_quality_parser_current_shape.py -q
python scripts/check_page_image_recognition_quality.py --write-json
python scripts/refresh_page_image_recognition_quality_summary.py
```
