# TRACE-Net LLM Graph-Path Compliance Judge v1

Read-only sampled evaluator for LLM graph-path compliance.

## Current tightening

This version adds `--use-checklist-prompt`, a short checklist-only prompt designed to reduce local model drift, malformed JSON, and repeated-token responses. It also accepts common key variants such as `graph_path_path_followed` during parsing so that near-compliant JSON can still be scored.

Safety contract: no Postgres writes, no Qdrant writes, no OpenSearch writes, no source-truth mutation, no answer permission, and no claim-proof authority.
