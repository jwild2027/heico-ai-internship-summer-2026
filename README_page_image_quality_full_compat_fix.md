# Page image-recognition quality full compatibility fix

This patch restores the public functions used by scripts/tests and normalizes the current image-recognition audit JSON shape.

It provides:

- `build_page_image_recognition_quality`
- `build_page_image_recognition_quality_report`
- `page_image_recognition_quality`
- `summarize_page_image_recognition_audit`
- `main`

Then run:

```bash
python -m pytest tests/unit/test_tiff_page_image_quality_parser_current_shape.py tests/unit/test_tiff_page_image_recognition_quality.py -q
python scripts/check_page_image_recognition_quality.py --write-json
python scripts/refresh_page_image_recognition_quality_summary.py
```
