# TRACE-Net E2E Dynamic Endpoint Tunnel Debug v4

Adds optional tunnel-debug metadata to the dynamic query endpoint response payload.

The endpoint can now load the v3 dynamic query tunnel report and expose:

- `tunnels_available`
- `missing_optional_tunnels`
- `tunnel_authority_contract`

This metadata is for explainability and debugging only. It does not grant answer authority, proof authority, source-truth mutation, or service writes. Graph and summary tunnels remain routing/ranking hints, not proof.

The dynamic endpoint still does not rerun OCR, page classification, embeddings, summaries, graph construction, table extraction, or source ingest.
