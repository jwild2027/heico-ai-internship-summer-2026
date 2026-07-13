# TRACE-Net Truthful OpenWebUI Live Stack v2

This patch replaces the demo-style OpenWebUI path with a truthful live path.

## Services

```text
OpenWebUI
   |
   v
8017 authenticated unified front door
   |-- 8014 real v27 request-time source-truth retrieval
   |-- 8016 real guided candidate discovery
   |-- strict confirmed visual retrieval
   |-- Qdrant semantic guidance
   |-- Engram behavior memory
   |-- Self-RAG critic / CRAG repair
```

## Fixed flaws

1. Replaces the canned 8014 smoke matcher with the v27 live orchestrator.
2. Starts the actual guided candidate-discovery endpoint instead of pointing the router at itself.
3. Strong checks require downstream HTTP 200, PASS quality, and real candidates/questions.
4. Removes answer-text-to-citation inference; citations require source record fields.
5. Exact visual part searches use field equality and exclude unrelated pages.
6. General visual ranking uses meaningful-token IDF plus Qdrant page guidance.
7. Qdrant is in the live path as guidance only and can never become proof.
8. OpenWebUI receives readable answers; internal routing data stays in `trace_net`.
9. Bounded multi-turn working memory carries active part/manual/figure entities.
10. Bearer API-key validation is enforced.
11. Request-size and concurrency limits are enforced.
12. Health checks verify exact service identity, artifact checksums, counts, graph/v2 guidance, Qdrant, and Engram.
13. `/v1/models`, non-streaming chat, and SSE streaming are supported.
14. Malformed/duplicate visual records fail startup in strict mode.
15. New runtime uses only Python standard library; no dependency drift is introduced.
16. Gemma drafts are shown only when citation IDs and extracted facts resolve to source evidence.
17. Engram hard-boundary rules are selected at request time.
18. Self-RAG critic and CRAG repair metadata are attached to every request.

## OpenWebUI

```text
Base URL: http://127.0.0.1:8017/v1
API key: trace-net-local
Model: trace-net-openwebui-unified-rag-v2
```

OpenWebUI is running in host network mode on this server, so `127.0.0.1` is correct.
