# Page image-recognition quality final module fix

This replaces `tiff/page_image_recognition_quality.py` with a compatibility module
that restores the public functions expected by tests and scripts while parsing
the current image-recognition audit JSON shape.

Run:

```bash
python -m pytest tests/unit/test_tiff_page_image_quality_parser_current_shape.py tests/unit/test_tiff_page_image_recognition_quality.py -q
python scripts/check_page_image_recognition_quality.py --write-json
python scripts/refresh_page_image_recognition_quality_summary.py
```
