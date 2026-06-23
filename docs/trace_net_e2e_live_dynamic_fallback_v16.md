# TRACE-Net E2E Live Dynamic Fallback v16

Adds a conservative dynamic fallback layer on top of the v15 live query pipeline.

The endpoint first reuses prebuilt v15 final-gated answers. If no v15 answer matches, it searches the prebuilt table exact-search adapter and builds a deterministic citation-backed answer only from exact source-truth table evidence. Queries with no exact source-truth evidence return an audit-only limitation.

Contract: no LLM call, no OCR rerun, no embedding rebuild, no graph rebuild, no table extraction rerun, no service writes, and no source-truth mutation.
