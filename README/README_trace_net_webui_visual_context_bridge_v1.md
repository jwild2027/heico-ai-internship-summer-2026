# TRACE-Net WebUI Visual Context Bridge v1

`trace_net_webui_visual_context_bridge_v1` converts the semantically validated LLaVA image visual summary into a small WebUI/Self-RAG context artifact.

It includes only visual cards where `webui_visual_context_allowed=true`, `semantic_validation_status=WEBUI_VISUAL_CONTEXT_ALLOWED`, and the LLaVA observation is clean. Review-only visual guesses are counted and excluded.

Safety contract:

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- visual context is retrieval guidance only, not source truth

Typical build:

```bash
python scripts/build_trace_net_webui_visual_context_bridge_v1.py \
  --image-visual-summary local_data/organization/trace_net/image_visual_summary_llava_12_semantic_ocr_join/trace_net_image_visual_summary_v1.json \
  --output-dir local_data/organization/trace_net/webui_visual_context_bridge \
  --quality
```

Typical quality check:

```bash
python scripts/check_trace_net_webui_visual_context_bridge_v1_quality.py \
  --report-path local_data/organization/trace_net/webui_visual_context_bridge/trace_net_webui_visual_context_bridge_v1.json \
  --write-json \
  --min-source-records 12 \
  --min-context-cards 1 \
  --min-excluded-records 1 \
  --require-source-quality-pass \
  --require-only-webui-allowed \
  --require-review-only-excluded \
  --max-unsafe 0 \
  --require-no-answer-permission \
  --require-no-source-truth-mutation \
  --require-no-write-attempts
```
