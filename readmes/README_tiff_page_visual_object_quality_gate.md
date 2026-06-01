# Page visual/object quality gate

Adds a quality-gate layer for the OCR/context-based page visual/object audit.

It validates that the page visual audit is present and that it includes:

- page role counts
- OCR/source/context coverage
- likely visual/table/figure signals
- graph linkage counts for page context, topic tags, and highlighted parts

Run:

```bash
python scripts/audit_page_visual_objects.py --write-json
python scripts/check_page_visual_object_quality.py --write-json
python scripts/refresh_page_visual_object_quality_summary.py
python scripts/apply_page_visual_quality_full_wrapper.py
python scripts/check_full_system_quality.py --require-page-visual-object-quality
```

This audit is OCR/context-based. It does not perform true image-region detection yet.
