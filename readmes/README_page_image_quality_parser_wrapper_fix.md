# Page image-recognition quality parser/wrapper fix

This patch fixes two issues:

1. `check_page_image_recognition_quality.py` now reads the current image-recognition audit JSON shape correctly, including `readable_images`.
2. `check_full_system_quality.py` accepts and runs `--require-page-image-recognition-quality` without forwarding that flag to the base pipeline checker.

Run:

```bash
python -m pytest tests/unit/test_tiff_page_image_quality_parser_fix.py -q
python scripts/check_page_image_recognition_quality.py --write-json
python scripts/refresh_page_image_recognition_quality_summary.py
python scripts/check_full_system_quality.py --require-api-adapter-quality --require-api-contract-tests --require-incremental-smoke --require-user-query-tests --require-realistic-query-trace --require-slow-realistic-query-trace --require-source-package-traceability --require-page-visual-object-quality --require-page-image-recognition-quality
```
