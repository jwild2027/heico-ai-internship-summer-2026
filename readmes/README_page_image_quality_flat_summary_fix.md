# Page image-recognition quality flat-summary fix

This patch replaces `tiff/page_image_recognition_quality.py` and adds a regression test for the generated audit JSON shape where image-recognition metrics live directly under `summary`.

It preserves compatibility with the older normalized shape:

```json
{
  "counts": {...},
  "image_recognition_signals": {...},
  "classification_counts": {...},
  "page_roles": {...}
}
```

It also supports the current generated shape:

```json
{
  "summary": {
    "pages_checked": 509,
    "images_readable": 509,
    "likely_visual_pages": 493,
    "likely_table_grid_pages": 331,
    "likely_figure_or_diagram_pages": 493,
    "average_ink_ratio": 0.068,
    "total_large_components": 17735,
    "classification_counts": {...},
    "role_counts": {...}
  },
  "records": []
}
```

Run:

```bash
python -m pytest tests/unit/test_tiff_page_image_quality_parser_current_shape.py tests/unit/test_tiff_page_image_recognition_quality.py -q
python scripts/check_page_image_recognition_quality.py --write-json && python scripts/refresh_page_image_recognition_quality_summary.py
```
