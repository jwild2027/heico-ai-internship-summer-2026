# TRACE-Net H30 Phase 4.2.0.1 — Navigation Latency Fastpath

## Observed bottleneck

For the exact-part navigation query:

`Which source document and page contain the strongest evidence for part 120-41824-003?`

the bridge returned its first SSE event in about 3 ms, Gemma was not called,
and the cognitive router spent approximately 44–46 seconds in retrieval.

The existing navigation path can launch five synchronous upstream requests:

1. the route's original unified request;
2. strongest-page fallback;
3. visual/diagram fallback;
4. guided candidate-page fallback;
5. direct-source fallback.

## Change

For `document_page_navigation` requests containing a full exact part number:

- allow the first upstream request;
- stop once an entity-matching page is present;
- otherwise allow at most one additional upstream request;
- retain the local artifact resolver;
- preserve existing critic, repair, rendering, and safety behavior;
- report each used/skipped tunnel and elapsed time.

The default maximum is two calls and can be adjusted from 1–5 with:

`TRACE_NET_NAVIGATION_MAX_UPSTREAM_CALLS`

## Unchanged

- all non-navigation routes;
- navigation requests without a full exact part number;
- evidence classification;
- source authority requirements;
- Self-RAG and CRAG rules;
- Postgres, Qdrant, OpenSearch, source files, and Engram state;
- answer permission and source-truth mutation policy.
