# TRACE-Net E2E Dynamic Query Endpoint v1

This module moves the WebUI demo from canned artifact replay toward query-time dynamic retrieval.

It **does not** rerun OCR, page classification, embeddings, summaries, graph construction, table extraction, source ingest, or corpus processing.

It consumes prebuilt artifacts, especially:

- `table_exact_search_adapter/trace_net_table_exact_search_adapter_v1.json`
- `table_hybrid_retrieval_bridge/trace_net_table_hybrid_retrieval_bridge_v1.json`

At query time it:

1. Classifies query intent.
2. Selects route/search channels.
3. Searches prebuilt table exact-search and table hybrid bridge records.
4. Builds citation/source-trace-ready dynamic response drafts.
5. Exposes `/api/trace-net/ask` and `/v1/chat/completions`.

Safety contract:

- no source truth mutation
- no direct answer permission
- no claim-proof authority
- no Postgres writes
- no Qdrant writes
- no OpenSearch writes/uploads

This is the first dynamic endpoint. Later versions should add Qdrant/page profiles, graph/community summaries, visual route summaries, and full final-gate runtime composition.
