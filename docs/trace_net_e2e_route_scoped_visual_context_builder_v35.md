# TRACE-Net Route-Scoped Visual Context Builder v35

v35 builds stored visual context cards for pages that already route to `image_visual`, diagram, callout, or technical drawing routes.

This stage is meant to plug into the existing OCR/classification route pipeline. It is not a new ingestion system and it does not answer user questions. It consumes stored page images plus optional route-dispatch metadata and writes reusable guidance-only visual context artifacts.

Outputs:

- `trace_net_route_scoped_visual_context_candidates_v35.jsonl`
- `trace_net_route_scoped_visual_context_cards_v35.jsonl`
- `trace_net_route_scoped_visual_prompt_context_v35.jsonl`
- `trace_net_route_scoped_visual_context_builder_v35.json`
- `trace_net_route_scoped_visual_context_builder_v35.md`

Safety contract:

- Visual context is guidance only.
- No answer permission is granted.
- No source-truth mutation is allowed.
- No writes to Postgres, Qdrant, or OpenSearch.
- Source-truth evidence is still required for factual part/manual claims.
