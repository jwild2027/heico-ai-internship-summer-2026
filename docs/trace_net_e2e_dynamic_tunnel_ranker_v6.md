# TRACE-Net E2E Dynamic Tunnel Ranker v6

Dynamic tunnel ranker v6 scores query-time evidence using prebuilt TRACE-Net artifacts and tunnel metadata.

It consumes existing table exact-search, table hybrid bridge, page/profile, page context, graph/community, route metadata, and table-route-summary artifacts. It does not rerun OCR, page classification, embeddings, summaries, graph construction, table extraction, source ingest, or service writes.

Graph and summaries are ranking/navigation hints only. They do not become proof authority, answer authority, or source truth.
