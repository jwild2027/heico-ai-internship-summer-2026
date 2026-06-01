# TIFF page image-recognition quality parser fix

Fixes the page image-recognition quality parser so it correctly reads the current audit JSON shape.

Run:

```bash
python -m pytest tests/unit/test_tiff_page_image_quality_parser_current_shape.py tests/unit/test_tiff_page_image_recognition_quality.py -q
python scripts/check_page_image_recognition_quality.py --write-json
python scripts/refresh_page_image_recognition_quality_summary.py
```
