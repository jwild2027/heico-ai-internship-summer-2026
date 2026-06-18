# TRACE-Net LLM Graph-Path Response Guard v1

Read-only QA module for checking whether an LLM response is anchored to a TRACE-Net graph/source card.

This module replaces self-grading JSON compliance with a safer pattern:

1. TRACE-Net resolves the page/source graph path.
2. The LLM receives a compact source-bound plain-text prompt.
3. TRACE-Net deterministically checks the response for target page ID, source identity, blank-page correctness, and forbidden proof/permission claims.

The `--enforce-source-anchor-prefix` option applies a system-owned prefix before scoring:

`Page <page_id> (<source_entry>) was resolved through the graph/source package path.`

This separates two things:

- the raw model response, reported through `model_response_*` counters
- the final guarded response, scored with deterministic source anchors

That matches production behavior: the system owns graph/source/path enforcement, and the LLM only writes a short bounded description.

It does not write to Postgres, Qdrant, or OpenSearch. It does not grant answer permission or claim-proof authority.
