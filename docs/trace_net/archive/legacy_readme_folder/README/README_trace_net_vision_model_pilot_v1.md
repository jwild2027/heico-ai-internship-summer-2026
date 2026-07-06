# TRACE-Net Vision Model Pilot v1

This module is Step 16.2 of the TRACE-Net front-start pipeline.

It builds a safe, advisory-only queue for pages that should be inspected by a vision-capable local model after deterministic ink/layout calibration.

## Purpose

The pilot answers this routing question:

```text
Which visual pages are worth sending to a vision model, and what should the model be asked to inspect?
```

It does **not** answer user questions and does **not** prove visual claims.

## Safety contract

Every pilot record is route-only:

```text
authority = visual_model_advisory_only
rag_bucket = vision_model_retrieval_helper
can_answer_directly = false
can_prove_claims = false
can_mutate_source_truth = false
final_answer_allowed = false
requires_ocr_compare = true
requires_graph_compare = true
requires_source_resolution = true
requires_citation = true
requires_authority_gate = true
```

If optional Ollama vision is run, the model output remains advisory and cannot be written as graph/source truth.

## Run plan-only mode

```bash
python scripts/build_trace_net_vision_model_pilot_v1.py \
  --visual-ink-layout-calibrator local_data/organization/trace_net/visual_ink_layout_calibrator/trace_net_visual_ink_layout_calibrator_v1.json \
  --figure-chart-understanding local_data/organization/trace_net/figure_chart_understanding/trace_net_figure_chart_understanding_v1.json \
  --image-recognition-audit local_data/organization/image_recognition/page_image_recognition_audit.json \
  --visual-text-records local_data/organization/visual_text/visual_text_extraction_clean.jsonl \
  --output-dir local_data/organization/trace_net/vision_model_pilot \
  --vision-mode plan-only \
  --max-pilot-pages 60 \
  --require-page-count 509 \
  --min-pilot-records 1 \
  --min-selected-pages 1 \
  --min-prompt-records 1 \
  --min-retrieval-only-records 1 \
  --quality
```

## Optional Ollama vision mode

Only use this if you have a vision-capable local Ollama model.

```bash
export OLLAMA_URL="http://localhost:11434"
export VISION_MODEL="llava:latest"

python scripts/build_trace_net_vision_model_pilot_v1.py \
  --visual-ink-layout-calibrator local_data/organization/trace_net/visual_ink_layout_calibrator/trace_net_visual_ink_layout_calibrator_v1.json \
  --figure-chart-understanding local_data/organization/trace_net/figure_chart_understanding/trace_net_figure_chart_understanding_v1.json \
  --image-recognition-audit local_data/organization/image_recognition/page_image_recognition_audit.json \
  --visual-text-records local_data/organization/visual_text/visual_text_extraction_clean.jsonl \
  --output-dir local_data/organization/trace_net/vision_model_pilot \
  --vision-mode ollama \
  --vision-model "$VISION_MODEL" \
  --ollama-url "$OLLAMA_URL" \
  --max-pilot-pages 10 \
  --max-model-error-count 10 \
  --quality
```

## Quality check

```bash
python scripts/check_trace_net_vision_model_pilot_v1_quality.py \
  --report-path local_data/organization/trace_net/vision_model_pilot/trace_net_vision_model_pilot_v1.json \
  --require-page-count 509 \
  --min-pilot-records 1 \
  --min-selected-pages 1 \
  --min-prompt-records 1 \
  --min-retrieval-only-records 1 \
  --write-json
```
