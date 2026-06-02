# Visual text v2.4 compact anti-leak prompt

This patch adds `visual_text_v2_4`, a more compact prompt designed to reduce
prompt-template leakage and section bleed seen in v2.2 outputs.

Key changes:

- Adds `--prompt-version visual_text_v2_4` / `v2_4`.
- Uses short `NONE` values instead of long placeholder instructions.
- Avoids phrases such as `bullet list of exact visible...` that LLaVA sometimes copied.
- Keeps metadata and OCR context separated from visible evidence sections.
- Adds `visual_text_v2_4_records` summary and `--require-v2-4` quality gate flag.

Recommended pilot:

```bash
python scripts/run_visual_text_extraction.py \
  --provider ollama \
  --model llava:13b \
  --max-pages 10 \
  --overwrite \
  --timeout-seconds 600 \
  --max-image-edge 1024 \
  --prompt-version visual_text_v2_4 \
  --ocr-max-chars 4000 \
  --fishnet

python scripts/refresh_visual_text_extraction_summary.py

python scripts/check_visual_text_extraction_quality.py \
  --write-json \
  --disallow-planned \
  --require-v2 \
  --require-v2-4 \
  --min-required-section-records 10 \
  --max-metadata-leakage-records 0 \
  --max-refusal-like-records 0

python scripts/postprocess_visual_text_outputs.py --open
```

The v2.3 cleanup/scoring layer should show fewer prompt-template leakage and
section-bleed records than the v2.2 run.
