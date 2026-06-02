# Visual Text Ollama LLaVA Fallback Fix

This patch changes the visual text extraction model auto-selection to prefer the
installed model that already returned non-empty output in the 509-page project:

- `llava:13b` is preferred before `qwen3-vl:latest`.
- `qwen3-vl:latest` remains available as a fallback/candidate, but it is no longer
  the first auto-selected model because it returned empty responses in this local
  Ollama setup.
- In `--model auto` mode, the Ollama client can try installed vision models in
  priority order instead of failing immediately on the first empty response.
- A small skip-record bug was fixed so skipped blank/missing-image records do not
  reference undefined provider/model variables.

Recommended pilot command:

```bash
python scripts/run_visual_text_extraction.py \
  --provider ollama \
  --model auto \
  --max-pages 2 \
  --overwrite \
  --timeout-seconds 600 \
  --max-image-edge 1600
```

With your installed models, `--model auto` should now select `llava:13b` first.

Quality check:

```bash
python scripts/check_visual_text_extraction_quality.py \
  --write-json \
  --disallow-planned
```
