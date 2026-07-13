# TRACE-Net Gated Visual Live Endpoint v1

This patch proves the live endpoint/OpenWebUI layer can call the gated image
visual route automatically.

## Endpoints

```text
GET  /health
POST /api/trace-net/visual-context
POST /api/trace-net/ask
POST /v1/chat/completions
```

## Inputs

```text
local_data/organization/trace_net/gated_visual_retrieval_adapter_v1_1/
  trace_net_gated_visual_retrieval_documents_v1_1.jsonl
```

Optional review-only input:

```text
local_data/organization/trace_net/gated_visual_retrieval_adapter_v1_1/
  trace_net_gated_visual_candidate_review_documents_v1_1.jsonl
```

## Safety

- no Ollama calls
- no LLM calls
- no OCR execution
- no database/vector/search writes
- no source-truth mutation
- no answer permission
- review-only visual candidates are counted but not used automatically
