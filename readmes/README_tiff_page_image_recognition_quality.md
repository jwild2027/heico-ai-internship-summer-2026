# TIFF page image-recognition quality gate

This patch adds a quality layer for the true TIFF image-recognition audit.

It checks that:

- the image-recognition audit JSON exists and is OK
- all page images are readable
- there are no missing/unreadable TIFF image files
- blank/nearly blank image count is within threshold
- visual/table/figure classifications are populated
- page roles are populated
- image-recognition graph overlay files exist

Run:

```bash
python scripts/audit_page_image_recognition.py --write-json --write-graph-overlay
python scripts/check_page_image_recognition_quality.py --write-json
python scripts/refresh_page_image_recognition_quality_summary.py
python scripts/apply_page_image_recognition_quality_full_wrapper.py
```

Then include the new flag in the full wrapper:

```bash
python scripts/check_full_system_quality.py \
  --require-api-adapter-quality \
  --require-api-contract-tests \
  --require-incremental-smoke \
  --require-user-query-tests \
  --require-realistic-query-trace \
  --require-slow-realistic-query-trace \
  --require-source-package-traceability \
  --require-page-visual-object-quality \
  --require-page-image-recognition-quality
```
