# TRACE-Net V2 Gemma summary sample runner v1 fix 2

This fixes OCR hydration when the fishnet OCR artifact stores text/page ids in a shape not recognized by fix 1.

Changes:
- Uses both default OCR files when present:
  - `trace_net_fishnet_ocr_grid_v1.json`
  - `trace_net_fishnet_ocr_grid_v1_cards.jsonl`
- Expands page-id detection:
  - `source_p000123`
  - `p000123`
  - `000123.tif`
  - rescarta-style `/000123` URLs
  - source/page/tiff/image/manual page number keys
- Expands OCR text extraction:
  - `ocr_text`, `text`, `raw_text`, `recognized_text`, `combined_text`, `best_text`
  - nested `lines`, `ocr_lines`, `cells`, `grid_cells`, `text_blocks`, `blocks`, `words`, `tokens`
- Adds OCR path/key samples to the run summary.

Safety remains unchanged: no DB/vector/search writes, no source-truth mutation, no answer permission.
