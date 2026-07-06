# TRACE-Net H39A Whole-Page Vision Summary v1

H39A is the formal whole-page image_visual vision route.

Purpose:
- take TRACE-Net image_visual routed source page images
- convert TIFF/page images to downscaled RGB JPEGs
- call a local vision model such as llama3.2-vision:11b through Ollama
- prompt with Engram-style cautious engineering guidance
- save JSON summaries as guidance-only artifacts

Safety contract:
- vision summaries are guidance only
- no answer permission
- no source-truth mutation
- no Postgres writes
- no Qdrant reads/writes
- no OpenSearch writes/uploads
- no approval/interchangeability/effectivity/fit/safety claims from vision alone

Recommended first run:
PYTHONPATH=. python -B scripts/build_trace_net_h39a_whole_page_vision_summary_v1.py   --llm-mode ollama   --model llama3.2-vision:11b   --max-pages 3   --vision-max-side 1024
