# TRACE-Net E2E API Wrapper Smoke v1

This module wraps the artifact-driven E2E RAG demo report into local API-style request and response records.

It is the bridge from artifact E2E to an eventual callable local endpoint.

## Contract

- It reads `trace_net_e2e_rag_demo_report_v1.json`.
- It writes local API-style request records and response draft records.
- It does not start a server.
- It does not call an LLM.
- It does not write to Postgres, Qdrant, or OpenSearch.
- It does not upload anything to OpenSearch.
- It does not mutate source truth.
- It does not grant direct answer/proof authority.

The response drafts remain smoke artifacts until the runtime API finalization layer is added.
