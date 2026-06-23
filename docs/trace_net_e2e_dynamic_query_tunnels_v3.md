# TRACE-Net E2E Dynamic Query Tunnels v3

Adds a query-time tunnel readiness/reporting layer for the dynamic endpoint.

This module does not rebuild corpus artifacts. It inspects already-built OCR/page-route/table/exact-search/profile/summary/graph artifacts and produces dynamic query tunnel plans that can be integrated into the endpoint runtime.

## Contract

- OCR is prebuilt.
- Page classification is prebuilt.
- Embeddings/Qdrant profiles are prebuilt.
- Page summaries/context are prebuilt.
- Graph/community metadata is prebuilt.
- Dynamic query tunnels are routing/ranking aids only.
- Graph and summaries are not proof authority.
- Answer permission remains blocked.
- Source truth mutation remains blocked.
- Postgres/Qdrant/OpenSearch writes remain blocked.

## Output

- `trace_net_e2e_dynamic_query_tunnels_v3.json`
- `trace_net_e2e_dynamic_query_tunnel_plans_v3.jsonl`
- `trace_net_e2e_dynamic_query_tunnels_v3.md`

## Intended next integration

The dynamic endpoint can consume this report to expose which prebuilt channels were available for a query: table exact-search, table bridge, page/profile/Qdrant, page summaries, graph/community navigation, route metadata, and table route handoff summary.
