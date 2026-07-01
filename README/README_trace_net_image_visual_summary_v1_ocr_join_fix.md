# TRACE-Net Image Visual Summary v1 OCR Join Fix

This focused patch fixes semantic validation OCR support for `trace_net_image_visual_summary_v1`.

Fishnet OCR grid v1.5 stores useful OCR evidence mainly in:

- `page_ocr_features.sample_text`
- `cell_records[*].sample_text`
- nested OCR word/token structures

The prior semantic validator only looked for top-level `ocr_text`-style fields, so all visual observations were marked review-only with `ocr_text_missing_for_semantic_support_check` even when OCR snippets existed in the fishnet record.

This patch expands `_ocr_text_from_record()` to collect those actual fishnet fields while preserving the safety contract: no source-truth mutation, no DB writes, no answer permission.
