# TRACE-Net Image Visual Summary v1

`trace_net_image_visual_summary_v1` builds structured visual-observation cards for pages routed to `image_visual`.

The module is artifact-only by default. In `dry_run` mode it proves the image route can be enumerated and prepared for vision-model observation without calling an LLM. In `ollama` mode it sends resolved page images to a local Ollama vision model such as `llava` and stores the model's visual observation as review/retrieval guidance.

## Safety contract

- No Postgres writes.
- No Qdrant writes.
- No OpenSearch writes.
- No source-truth mutation.
- No direct answer permission.
- No engineering approval, safe-to-install, interchangeability, or airworthiness claims.
- Vision output is guidance only and requires OCR/source citation confirmation before answers.

## Inputs

- `fishnet_route_dispatch_handoff/trace_net_fishnet_route_dispatch_handoff_v1.json`
- Optional `fishnet_ocr_grid/trace_net_fishnet_ocr_grid_v1.json`
- Optional source package such as `/c/Users/juswil/Desktop/metadata.zip`

## Output

`local_data/organization/trace_net/image_visual_summary/trace_net_image_visual_summary_v1.json`

The report includes:

- `records` / `visual_summary_cards`
- `visual_model_execution_status`
- `image_source_status`
- `visual_observation`
- safety counters
- source/route trace metadata

## Typical dry-run command

```bash
python scripts/build_trace_net_image_visual_summary_v1.py \
  --route-dispatch-handoff local_data/organization/trace_net/fishnet_route_dispatch_handoff/trace_net_fishnet_route_dispatch_handoff_v1.json \
  --fishnet-ocr-grid local_data/organization/trace_net/fishnet_ocr_grid/trace_net_fishnet_ocr_grid_v1.json \
  --source-package /c/Users/juswil/Desktop/metadata.zip \
  --output-dir local_data/organization/trace_net/image_visual_summary \
  --vision-mode dry_run \
  --max-image-pages 20 \
  --write-image-copies \
  --quality
```

## Optional LLaVA/Ollama command

```bash
python scripts/build_trace_net_image_visual_summary_v1.py \
  --route-dispatch-handoff local_data/organization/trace_net/fishnet_route_dispatch_handoff/trace_net_fishnet_route_dispatch_handoff_v1.json \
  --fishnet-ocr-grid local_data/organization/trace_net/fishnet_ocr_grid/trace_net_fishnet_ocr_grid_v1.json \
  --source-package /c/Users/juswil/Desktop/metadata.zip \
  --output-dir local_data/organization/trace_net/image_visual_summary_llava_smoke \
  --vision-mode ollama \
  --vision-model llava \
  --ollama-base-url http://127.0.0.1:11434 \
  --request-timeout 240 \
  --max-image-pages 3 \
  --write-image-copies \
  --quality
```
