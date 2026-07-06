# TRACE-Net H27D Engram answer-smoke overlay map patch

Adds explicit opt-in `--engram-answer-runner-overlay-map` support to the real engineering LLM answer-smoke builder.

Safety contract: artifact/prompt-only; no Postgres writes, no Qdrant writes, no OpenSearch writes, no source-truth mutation, and no answer permission from Engram overlays.
