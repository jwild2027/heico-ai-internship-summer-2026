# TRACE-Net WebUI Self-RAG / CRAG Bridge v1

Quality status: **PASS**

## Question

`Find part number 120-29073-001 and nearby similar parts. Use every TRACE-Net evidence route that is available and show source boundaries.`

## Summary

- Used tools: `['query_planner', 'context_pack_blueprint', 'context_pack_builder', 'self_rag', 'route_dispatch', 'table_route', 'page_context_v2', 'graph_leiden', 'visual_image_route', 'webui_visual_context_bridge']`
- CRAG retry status: `skipped_not_needed`
- Self-RAG status counts: `{'READY_FOR_GEMMA_DRAFT_CONTEXT_ONLY': 1}`
- CRAG retry plans: `0`
- Evidence capsules: `30`
- Visual context cards: `2`
- Review-only visual cards excluded: `10`

## Checklist

```text
query planner: used — stage report built with quality_status=PASS
context pack blueprint: used — stage report built with quality_status=PASS
context pack builder: used — stage report built with quality_status=PASS
Self-RAG: used — stage report built with quality_status=PASS
CRAG retry: skipped_not_needed — Self-RAG did not require CRAG retry; CRAG report was still evaluated with zero retry plans
route/dispatch: used — context pack builder selected/loaded 1019 records from fishnet_route_dispatch_handoff
table/route: used — context pack builder selected/loaded 1515 records from table_exact_search_adapter
page/context/v2: used — context pack builder selected/loaded 510 records from page_context_v2
graph/leiden: used — context pack builder selected/loaded 20000 records from leiden_communities
visual/image/route: used — safe WebUI visual context bridge supplied 2 OCR-supported visual card(s); 10 review-only visual card(s) excluded
webui visual context bridge: used — loaded 2 safe visual context card(s); excluded 10 review-only visual card(s)
embedding/vector: not_wired_in_bridge — this bridge uses the current context-pack artifacts; live vector search is not yet a stage input here
Gemma LLM: not_called_by_design — this bridge stops before drafting so Self-RAG/CRAG can be audited separately
final gate: not_called_by_design — no answer draft is produced by this bridge, so final gate is not invoked here
```

## Safety

- unsafe_record_count: `0`
- answer_permission_count: `0`
- can_answer_directly_count: `0`
- can_prove_claims_count: `0`
- source_truth_mutation_allowed_count: `0`
- postgres_write_attempt_count: `0`
- qdrant_write_attempt_count: `0`
- opensearch_write_attempt_count: `0`