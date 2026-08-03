# TRACE-Net H30 Final Semantic Acceptance Gate v1.1

## Repair to v1

The v1 installer escaped a Python docstring inside generated source code and
wrote repository files before its compile check. This could leave the benchmark
runner partially modified with a syntax error.

The v1.1 installer:

- recognizes and repairs the partially applied v1 state;
- builds every target file completely in memory;
- compiles the target Python source before writing any destination;
- treats CRLF and LF as equivalent;
- remains idempotent.

## Semantic acceptance behavior

A Gemma answer is accepted only after it passes both the renderer-specific
validator and the same full semantic evaluator used for the final benchmark
answer. If either validator fails, the bounded deterministic draft is used.
Raw model output and raw failure reasons remain recorded.

## Safety

This change does not promote candidate, semantic, visual, graph, OCR, summary,
or table-derived guidance into source truth. It does not change routing,
retrieval, Postgres, Qdrant, OpenSearch, or source-truth mutation policy.
