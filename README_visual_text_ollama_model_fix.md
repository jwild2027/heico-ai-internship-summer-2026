# Visual text extraction Ollama model fix

This patch makes the visual text extraction layer friendlier for local Ollama setups.

## What changed

- The default visual model is now `auto`.
- `auto` checks `http://127.0.0.1:11434/api/tags` and selects an installed vision-capable model.
- It prefers `qwen3-vl:latest` when installed, then falls back to `llava:13b`, `llava:latest`, and other vision-like model names.
- `--list-ollama-models` prints installed models and marks the auto-selected vision model.
- Ollama HTTP errors now include clearer model suggestions.
- Summary JSON now records the actual client/model used, including `mock-vision-model` for mock runs and the resolved Ollama tag for `auto`.

## Why this was needed

The previous command used:

```bash
--model llava:latest
```

but the local Ollama install had:

```text
llava:13b
qwen3-vl:latest
```

not `llava:latest`. Ollama therefore returned HTTP 404.

## Recommended commands

List models and see what auto will pick:

```bash
python scripts/run_visual_text_extraction.py --list-ollama-models
```

Run a tiny real-model pilot with auto selection:

```bash
python scripts/run_visual_text_extraction.py \
  --provider ollama \
  --model auto \
  --max-pages 2 \
  --overwrite \
  --timeout-seconds 600 \
  --max-image-edge 1600
```

Run explicitly with qwen3-vl:

```bash
python scripts/run_visual_text_extraction.py \
  --provider ollama \
  --model qwen3-vl:latest \
  --max-pages 2 \
  --overwrite \
  --timeout-seconds 600 \
  --max-image-edge 1600
```

Run explicitly with llava:13b:

```bash
python scripts/run_visual_text_extraction.py \
  --provider ollama \
  --model llava:13b \
  --max-pages 2 \
  --overwrite \
  --timeout-seconds 600 \
  --max-image-edge 1600
```

Then check quality:

```bash
python scripts/check_visual_text_extraction_quality.py --write-json --disallow-planned
```
