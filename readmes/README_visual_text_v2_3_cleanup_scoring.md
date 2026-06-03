# Visual text v2.3 cleanup/scoring layer

This patch adds a postprocessing layer for the visual-text extraction pipeline. It does not call Ollama and does not reprocess TIFFs. It reads the existing visual-text JSONL records, cleans common model formatting issues, scores review risks, assigns a trust tier, and writes clean review artifacts.

## New files

```text
tiff/visual_text_cleanup.py
scripts/postprocess_visual_text_outputs.py
scripts/check_visual_text_clean_quality.py
tests/unit/test_tiff_visual_text_cleanup.py
tests/unit/test_tiff_visual_text_cleanup_quality.py
README_visual_text_v2_3_cleanup_scoring.md
```

## What it detects

```text
prompt-template leakage
section bleed
metadata leakage
refusal-like text
summary-heavy text
hallucination-risk phrases
table expected but not extracted
unsupported visual part numbers
trust tier A/B/C/D
```

## Run

```bash
python scripts/postprocess_visual_text_outputs.py --open
```

Then check quality:

```bash
python scripts/check_visual_text_clean_quality.py \
  --write-json \
  --min-records 25 \
  --max-metadata-leakage-records 0 \
  --max-refusal-like-records 0 \
  --max-prompt-template-leakage-records 0 \
  --max-trust-d-records 0
```

A stricter quality run can also require a minimum number of RAG-usable records:

```bash
python scripts/check_visual_text_clean_quality.py \
  --write-json \
  --min-records 25 \
  --min-usable-for-rag-records 1 \
  --max-metadata-leakage-records 0 \
  --max-refusal-like-records 0 \
  --max-prompt-template-leakage-records 0 \
  --max-trust-d-records 0
```

## Outputs

```text
local_data/organization/visual_text/visual_text_extraction_clean.jsonl
local_data/organization/visual_text/visual_text_clean_summary.json
local_data/organization/visual_text/visual_text_review_flags.json
local_data/organization/visual_text/visual_text_clean_corpus.md
local_data/organization/visual_text/visual_text_clean_review.md
local_data/organization/visual_text/visual_text_clean_review.html
local_data/organization/visual_text/visual_text_clean_quality.json
```

## Trust tiers

```text
A = clean useful visual context
B = clean but low detail
C = review needed, usually table-missing/section-bleed/hallucination risk
D = reject for RAG, usually metadata leakage, refusal, or prompt-template leakage
```

The clean output is still derived visual context. It should not replace canonical OCR, source TIFF evidence, or the part catalog.
