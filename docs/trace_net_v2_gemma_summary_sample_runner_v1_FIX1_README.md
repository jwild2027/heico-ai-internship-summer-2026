# TRACE-Net V2 Gemma summary sample runner v1 fix 1

This fixes the first live Gemma sample issue:

- The runner was sending pages with little/no OCR text to Gemma, so Gemma correctly returned generic "no OCR content" summaries.
- It stopped after exactly 5 selected candidates, so one transient error left only 4 completed records.

Changes:

- Adds optional OCR hydration from local JSON/JSONL artifacts.
- Automatically uses `local_data/organization/trace_net/fishnet_ocr_grid/trace_net_fishnet_ocr_grid_v1.json` when present.
- Adds `--ocr-records` for explicit OCR artifacts.
- Adds `--require-ocr-text` so Gemma only receives pages with usable OCR/text.
- Adds `--max-candidate-pages` so the runner can try more than 5 pages to get 5 successful Gemma summaries.
- Records candidate/attempt/hydration counts in the summary.

Safety remains unchanged: no DB/vector/search writes, no source-truth mutation, no answer permission.
