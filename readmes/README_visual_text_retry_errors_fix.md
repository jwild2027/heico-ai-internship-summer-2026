# Visual text retry-errors fix

This patch improves long-running visual text extraction batches.

## What changed

- Adds per-page retry mode:
  - `--retry-errors-only`
  - preserves existing successful visual-text records
  - reprocesses only pages whose existing record has `status=error`
- Keeps checkpoint/progress behavior from the previous patch.
- Changes mixed runs from `FAIL` to `PARTIAL` when some pages succeed and some fail.
- Adds optional quality-gate tolerance for partial pilot runs:
  - `--allow-partial-status`
  - `--max-error-records N`

## Why

A 25-page Ollama/LLaVA run can have a couple slow pages that hit the timeout. Before this patch, retrying required overwriting the batch or manually selecting page IDs. Now you can retry only failed pages and keep the successful records.

## Recommended retry for the two timeout pages

```bash
python scripts/run_visual_text_extraction.py \
  --provider ollama \
  --model llava:13b \
  --retry-errors-only \
  --timeout-seconds 1200 \
  --max-image-edge 768
```

Then check strict quality:

```bash
python scripts/check_visual_text_extraction_quality.py \
  --write-json \
  --disallow-planned
```

If the same pages still time out and you want to accept the 23/25 pilot as a useful partial pilot, use:

```bash
python scripts/check_visual_text_extraction_quality.py \
  --write-json \
  --disallow-planned \
  --allow-partial-status \
  --max-error-records 2
```

Strict mode remains the default.
