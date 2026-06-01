# Page image quality dual API fix

This patch preserves both public APIs:

- `build_page_image_recognition_quality_report(...)` returns the object-style quality report used by scripts.
- `build_page_image_recognition_quality(...)` returns a plain dictionary for older tests/callers.

Apply with:

```bash
python scripts/apply_page_image_quality_dual_api_fix.py
```
