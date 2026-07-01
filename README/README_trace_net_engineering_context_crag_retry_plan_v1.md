# TRACE-Net Engineering Context CRAG Retry Plan v1.1

Builds corrective retrieval/repackaging plans for engineering context packs that failed Self-RAG checks.

v1.1 fixes:
- deduplicates retry actions
- avoids unknown target routes when structured route-specific missing evidence exists
- adds unknown_target_route_count quality visibility

It does not execute retrieval, call an LLM, answer the user, write DBs, mutate source truth, or grant answer permission.
