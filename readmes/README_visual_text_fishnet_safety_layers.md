# Visual text fishnet safety layers

This patch adds an opt-in layered retry system for model-assisted visual text extraction.

The normal batch still runs first. If a page fails, the page falls through configured safety layers, usually smaller image sizes plus longer timeouts. Good records are preserved; only the failed page is retried inside the current run.

## Built-in fishnet

```bash
python scripts/run_visual_text_extraction.py \
  --provider ollama \
  --model llava:13b \
  --max-pages 25 \
  --overwrite \
  --timeout-seconds 600 \
  --max-image-edge 1024 \
  --prompt-version visual_text_v2_2 \
  --ocr-max-chars 4000 \
  --fishnet
```

Built-in layers:

```text
primary:     max_image_edge=1024, timeout=600   # from your command
rescue_768:  max_image_edge=768,  timeout=1200
rescue_512:  max_image_edge=512,  timeout=1200
```

## Custom fishnet

```bash
python scripts/run_visual_text_extraction.py \
  --provider ollama \
  --model llava:13b \
  --max-pages 25 \
  --overwrite \
  --timeout-seconds 600 \
  --max-image-edge 1024 \
  --prompt-version visual_text_v2_2 \
  --ocr-max-chars 4000 \
  --safety-layers rescue_768:768:1200,rescue_512:512:1200
```

Layer format:

```text
name:max_image_edge:timeout_seconds[:temperature][:ocr_max_chars][:ocr|noocr][:prompt][:model]
```

Examples:

```text
rescue_768:768:1200
rescue_512:512:1200
noocr_768:768:1200:0.0:0:noocr
```

## What gets recorded

Each output record now includes:

```text
fishnet_layer
fishnet_layer_index
fishnet_rescued
fishnet_attempts
max_image_edge
timeout_seconds
temperature
```

The summary now includes:

```text
fishnet_safety_layers_enabled
fishnet_safety_layer_count
fishnet_safety_layers
fishnet_rescued_records
fishnet_failed_records
fishnet_attempt_total
fishnet_layer_counts
```

## Why

This makes long visual extraction runs safer. Timeout-prone pages can automatically fall into progressively smaller/slower rescue settings instead of failing the whole batch and requiring a separate manual retry command.
