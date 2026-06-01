# Page image-recognition quality complete replacement

This patch replaces `tiff/page_image_recognition_quality.py` with a stable compatibility implementation.
It supports both object-style and dictionary-style callers and parses the current image-recognition audit JSON shape.

Run:

```bash
python -m pytest tests/unit/test_tiff_page_image_quality_parser_current_shape.py tests/unit/test_tiff_page_image_recognition_quality.py -q
python scripts/check_page_image_recognition_quality.py --write-json
python scripts/refresh_page_image_recognition_quality_summary.py
```
