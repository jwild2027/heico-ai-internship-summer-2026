# Clean replacement notes

This zip is intended to be unzipped at the repository root.

It overwrites:

- `tiff/page_image_recognition_quality.py`
- `tests/unit/test_tiff_page_image_quality_parser_current_shape.py`

The replacement keeps the historical parser behavior and adds support for the current generated audit shape where page counts, readable image counts, visual signal counts, ink metrics, role counts, classification counts, and overlay paths live under `audit["summary"]`.
