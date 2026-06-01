# Visual text v2.2 CLI choice fix

This patch fixes the CLI parser for `scripts/run_visual_text_extraction.py` so it accepts the v2.2 prompt values:

```bash
--prompt-version visual_text_v2_2
--prompt-version v2_2
```

The previous v2.2 patch updated the extraction engine and quality checker, but the `argparse` choices in `tiff/visual_text_extraction.py` still only allowed v1, v2, and v2.1. As a result, the extraction command rejected v2.2 before it could run.

## Verify

```bash
python -m pytest \
  tests/unit/test_tiff_visual_text_extraction.py \
  tests/unit/test_tiff_visual_text_extraction_quality.py \
  tests/unit/test_tiff_visual_text_ollama_model_selection.py \
  tests/unit/test_tiff_visual_text_progress.py \
  tests/unit/test_tiff_visual_text_retry_errors.py \
  tests/unit/test_tiff_visual_text_output_report.py \
  tests/unit/test_tiff_visual_text_strict_v2.py \
  tests/unit/test_tiff_visual_text_metadata_leakage.py \
  tests/unit/test_tiff_visual_text_v2_2_leak_refusal_fix.py \
  tests/unit/test_tiff_visual_text_v2_2_cli_choice.py \
  -q
```

## Run

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
