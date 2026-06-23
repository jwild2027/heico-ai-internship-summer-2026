# TRACE-Net E2E Live Query Pipeline v15

This stage adds a live query-time orchestration endpoint on top of the v14 final-answer endpoint.

It exposes the same OpenAI-compatible routes used by Open WebUI, but returns a richer `trace_net` payload showing the query path through:

1. dynamic retrieval
2. tunnel ranking
3. context pack
4. Self-RAG critic
5. CRAG corrector
6. LLM prompt contract
7. reasoned response draft
8. final answer gate
9. WebUI final answer

The stage is intentionally conservative. It serves only final-gated answers that already passed v13. Unknown queries return an audit-only limitation saying the dynamic pipeline must execute before a final answer can be returned.

The endpoint does not call an LLM, rerun retrieval, rerun OCR, rebuild embeddings, rebuild graph, rerun table extraction, mutate source truth, or write to services.
