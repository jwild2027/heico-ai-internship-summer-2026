# Page image recognition quality final actual fix

Replaces `tiff/page_image_recognition_quality.py` with a robust parser that supports:

- current audit JSON shape
- older unit-test fixture shape
- object-style and dict-style public APIs
- graph overlay node/edge counts

Expected after applying:

```bash
python -m pytest tests/unit/test_tiff_page_image_quality_parser_current_shape.py tests/unit/test_tiff_page_image_recognition_quality.py -q
python scripts/check_page_image_recognition_quality.py --write-json
```

should report readable images and classifications correctly.
