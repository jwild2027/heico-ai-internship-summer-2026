# TRACE-Net Gemma Visual Live Router v1

This patch performs steps 1–3:

1. **Live visual endpoint swap**  
   Adds `serve_trace_net_gemma_visual_live_endpoint_v1.py`, which serves the
   cleaned Gemma visual retrieval docs.

2. **Router/proxy integration**  
   Adds `serve_trace_net_router_proxy_v6_gemma_visual_v1.py`, which routes
   diagram/figure/callout questions to `gemma_confirmed_image_visual` and leaves
   exact/partial part lookups to the normal/guided routes.

3. **3-route smoke test**  
   Adds `run_trace_net_gemma_visual_3_route_live_smoke_v1.py`, which checks:
   - visual general query -> Gemma visual route
   - visual exact part diagram query -> Gemma visual route
   - exact part query -> not visual
   - partial part query -> guided/partial, not visual

## Input

```text
local_data/organization/trace_net/confirmed_image_gemma_visual_retrieval_cleaner_v1_full/trace_net_confirmed_image_gemma_visual_clean_retrieval_documents_v1.jsonl
```

## Safety

The new route is retrieval guidance only:

- `answer_permission=false`
- `final_answer_allowed=false`
- no Ollama/LLM calls in visual route
- no Postgres/Qdrant/OpenSearch writes
- no source-truth mutation


## v1 fix

The first laptop test exposed a unit-test fallback bug: when the existing v6 base
router is present but `base_config=None`, the wrapper tried to call:

```text
base_router.route_payload(payload, None)
```

The fix delegates to the real base router only when `config.base_config` exists.
Otherwise, it uses the safe local stub fallback. Production still delegates
normally because `build_config()` creates the real base config.
