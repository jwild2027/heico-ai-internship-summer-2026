# TIFF page-context OCR path fix

This patch makes page-context generation read the same OCR/TIFF path aliases used by the organization export and query helper, especially `ocr_text_path` and `source_image_path`.

Without this, Gemma context generation can succeed but every context may still carry a `missing_ocr` warning because `generate_page_contexts.py` cannot find the OCR path field in `page_index.json`.

Run:

```bash
python -m pytest tests/unit/test_tiff_page_context_graph.py -q
python scripts/generate_page_contexts.py --model gemma3:12B --limit 25 --force --write-json --show-error-details
python scripts/export_document_organization_graph.py --strict
```

Expected: `model_fallback` should stay gone and `missing_ocr` should only appear for pages that truly do not have an OCR path.
