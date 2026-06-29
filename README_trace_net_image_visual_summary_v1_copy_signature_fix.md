# TRACE-Net Image Visual Summary v1 copy/extract signature fix

This focused fix completes the OCR semantic-validation plumbing introduced by the semantic validator patch.

## Fix

`build_image_visual_summary()` passes `ocr_text_lookup` into `_visual_summary_card()`, and `_visual_summary_card()` now passes the same lookup into `_copy_or_extract_image()`.

Without this, dry-run and LLaVA builds fail before image resolution with:

```text
TypeError: _copy_or_extract_image() missing 1 required keyword-only argument: 'ocr_text_lookup'
```

## Safety

The module remains artifact-only:

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
