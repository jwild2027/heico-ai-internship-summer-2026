# Visual text extraction strict v2

This patch upgrades the visual-text extraction layer from a loose visual summary prompt to a stricter model-assisted OCR prompt.

## What changed

- Default prompt version is now `visual_text_v2`.
- Existing OCR text is included in the prompt by default when `source.ocr_path` is available.
- The prompt now requires transcription first and summary second.
- The model is told to use `unreadable` instead of guessing unclear cells or labels.
- Every successful record is normalized into a fixed section layout:
  - Page type
  - Visible title/header
  - Transcribed visible text
  - Visual summary
  - Tables
  - Figures/diagrams
  - Charts/graphs
  - Labels/callouts/part numbers
  - Warnings/notes
  - Uncertain/unreadable
  - Model caution
- Records now include `visual_text_scores` for review and quality checks.
- The output viewer now shows extraction scores and OCR-assist previews.
- The quality gate has optional stricter v2 checks.

## Safe 25-page v2 pilot

```bash
python scripts/run_visual_text_extraction.py \
  --provider ollama \
  --model llava:13b \
  --max-pages 25 \
  --overwrite \
  --timeout-seconds 600 \
  --max-image-edge 1024 \
  --prompt-version visual_text_v2 \
  --ocr-max-chars 4000
```

Retry any failed pages only:

```bash
python scripts/run_visual_text_extraction.py \
  --provider ollama \
  --model llava:13b \
  --retry-errors-only \
  --timeout-seconds 1200 \
  --max-image-edge 768 \
  --prompt-version visual_text_v2 \
  --ocr-max-chars 4000
```

Strict quality check:

```bash
python scripts/check_visual_text_extraction_quality.py \
  --write-json \
  --disallow-planned \
  --require-v2 \
  --min-required-section-records 25
```

Review outputs:

```bash
python scripts/print_visual_text_outputs.py \
  --write-md \
  --write-html \
  --open
```

## Important note

`visual_text_scores.hallucination_risk` is a review flag, not proof of a hallucination. It marks wording such as `likely`, `appears to`, or `may be`, which may be acceptable in a visual summary but should not be promoted into verified facts without source review.
