# Visual Text v2.1 Metadata Leakage Fix

This patch tightens the visual-text extraction layer so model output separates true visible transcription from metadata/OCR/context hints.

## What changed

- Default prompt version is now `visual_text_v2_1`.
- Adds a required `OCR/context assist notes` section.
- Prompt explicitly says metadata and OCR assist are context only, not visible page text.
- Adds metadata-leakage scoring on visible-evidence sections:
  - `metadata_leakage_risk`
  - `metadata_leakage_markers`
  - `metadata_leakage_marker_count`
- Adds summary counters:
  - `visual_text_ocr_context_note_records`
  - `visual_text_metadata_leakage_records`
  - `visual_text_metadata_leakage_marker_total`
- Adds quality gate option:
  - `--max-metadata-leakage-records`
- Updates terminal/HTML review output to show metadata leakage scoring.

## Why

v2 was correctly structured, but some outputs copied prompt metadata into visible extraction fields, for example:

```text
current page role: parts_list
image classification: likely_table_or_grid
source URL/path hint: http://localhost:8080/...
existing context summary: ...
```

v2.1 gives the model a safe section for context-only information and lets the quality gate block leakage before larger 50-page or 509-page runs.

## Recommended run

```bash
python scripts/run_visual_text_extraction.py \
  --provider ollama \
  --model llava:13b \
  --max-pages 10 \
  --overwrite \
  --timeout-seconds 600 \
  --max-image-edge 1024 \
  --prompt-version visual_text_v2_1 \
  --ocr-max-chars 4000
```

Then check quality strictly:

```bash
python scripts/check_visual_text_extraction_quality.py \
  --write-json \
  --disallow-planned \
  --require-v2 \
  --min-required-section-records 10 \
  --max-summary-heavy-records 0 \
  --max-metadata-leakage-records 0
```

If metadata leakage remains above zero, inspect the review page:

```bash
python scripts/print_visual_text_outputs.py --write-md --write-html --open
```

