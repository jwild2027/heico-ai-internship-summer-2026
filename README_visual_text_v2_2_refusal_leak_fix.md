# Visual text v2.2 metadata-leak/refusal fix

This patch keeps the v2.1 metadata-leakage protections, but reduces the failure mode where `llava:13b` responds with text such as "I'm unable to transcribe text from images."

## What changed

- Default prompt version is now `visual_text_v2_2`.
- The prompt tells the local vision model it can read/describe the supplied page image.
- Metadata is still isolated from visible-page sections.
- OCR/context-only hints must go under `OCR/context assist notes`.
- The parser now accepts markdown headings, plain section labels, and setext-style headings such as:

```text
Page type
---------
parts_list
```

- Scores now include `refusal_like`.
- Quality gate supports:

```bash
--require-v2-2
--max-refusal-like-records 0
```

## Recommended test run

```bash
python scripts/run_visual_text_extraction.py \
  --provider ollama \
  --model llava:13b \
  --max-pages 10 \
  --overwrite \
  --timeout-seconds 600 \
  --max-image-edge 1024 \
  --prompt-version visual_text_v2_2 \
  --ocr-max-chars 4000
```

Then:

```bash
python scripts/check_visual_text_extraction_quality.py \
  --write-json \
  --disallow-planned \
  --require-v2 \
  --require-v2-2 \
  --min-required-section-records 10 \
  --max-metadata-leakage-records 0 \
  --max-refusal-like-records 0
```

Optional strict summary check:

```bash
python scripts/check_visual_text_extraction_quality.py \
  --write-json \
  --disallow-planned \
  --require-v2 \
  --require-v2-2 \
  --min-required-section-records 10 \
  --max-metadata-leakage-records 0 \
  --max-refusal-like-records 0 \
  --max-summary-heavy-records 0
```

Use the optional summary-heavy check only after verifying that the local model is producing real page content rather than refusal/template text.
