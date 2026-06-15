# TRACE-Net LLM Graph-Path Compliance Judge v1

Read-only sampled evaluator for Page Retrieval Large Eval v2 LLM graph-path cards.

This module checks whether a local Ollama model follows the required graph/source path before answering. It is an offline QA harness, not the normal user-query path.

Safety contract:

- No Postgres writes
- No Qdrant writes
- No OpenSearch writes
- No source-truth mutation
- No answer permission
- No claim-proof authority

The Ollama call wrapper supports JSON mode, bounded `num_predict`, retries, and report-visible retry settings. This helps distinguish prompt-format failures from local model timeout/cold-load failures.


## Text fallback mode

Use `--allow-text-fallback` for local Ollama models that return prose instead of strict JSON. The judge still records `json_format_violation_count`, but can score graph-path compliance from text when the response anchors to the target page and confirms source/Dublin/TIFF identity. Retrieval, Leiden/community, and category signals remain non-proof.
