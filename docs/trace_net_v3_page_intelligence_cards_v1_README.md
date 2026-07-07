# TRACE-Net V3 Page Intelligence Cards v1

Builds V3 page-intelligence cards from existing artifacts without rerunning the LLM.

Inputs:
- Fishnet OCR grid report: `trace_net_fishnet_ocr_grid_v1.json`
- Accepted Gemma V2 page context records: `trace_net_page_context_v2_records.json`
- Deferred V2 page IDs, if any

Outputs:
- `trace_net_v3_page_intelligence_cards_v1.json`
- `trace_net_v3_page_intelligence_cards_v1.jsonl`
- `trace_net_v3_page_intelligence_graph_nodes.json`
- `trace_net_v3_page_intelligence_graph_edges.json`
- `trace_net_v3_page_intelligence_cards_v1_quality.json`

Graph convention:
- `page::<page_id> -[:HAS_V3_PAGE_INTELLIGENCE]-> v3_page_intelligence::<page_id>`

Safety contract:
- V3 is retrieval/routing guidance only.
- V3 is not canonical source truth.
- V3 cannot answer directly.
- V3 cannot prove claims.
- No Postgres, Qdrant, or OpenSearch writes occur in this build.
