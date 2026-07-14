# TRACE-Net Router Proxy v6 + Gated Visual Route v1

This patch creates the main 8017 router/proxy integration for the gated visual
route.

It does **not** replace the existing v6 guided/normal router logic. It imports
the current repo's:

```text
scripts/serve_trace_net_guided_discovery_router_proxy_v6.py
```

and uses it as fallback for normal/guided routing.

It also imports:

```text
scripts/serve_trace_net_gated_visual_live_endpoint_v1.py
```

for the gated visual route logic.

## Route order

```text
visual/diagram/figure/callout query
→ gated_image_visual route
→ only confirmed search-ready visual docs

nonvisual query
→ existing v6 router fallback
→ normal_ask or guided_discovery
```

Forced modes like `mode=guided`, `mode=normal`, or `mode=chat` still go to the
existing v6 fallback unless `mode=visual` or `mode=gated_image_visual` is used.

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

## Endpoints

```text
GET  /health
POST /api/trace-net/router
POST /api/trace-net/ask
POST /v1/chat/completions
```

## Safety

- visual route is read-only
- no visual-route Ollama call
- no visual-route LLM call
- no source-truth mutation
- no Postgres/Qdrant/OpenSearch write
- `final_answer_allowed=false`
- `answer_permission=false`
- review-only visual candidates are excluded from automatic context
