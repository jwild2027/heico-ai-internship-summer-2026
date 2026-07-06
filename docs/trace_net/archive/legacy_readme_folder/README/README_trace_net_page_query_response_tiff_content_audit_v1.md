# TRACE-Net Page Query Response TIFF Content Audit v1

Read-only audit module that opens source TIFF files from `metadata.zip` and checks whether the page query/response dataset is visually consistent with the actual page image.

This module is not a final answer API. It does not grant answer authority, proof authority, source-truth mutation, or index writes.

## Modes

- Image heuristic mode: opens every TIFF, computes ink/blank/table-like metrics, checks blank response behavior and page/source anchors.
- Optional Ollama vision mode: sends sampled or full TIFF images plus the generated answer to a local vision model such as `qwen3-vl:latest` or `llava:13b` and records PASS/REVIEW/FAIL.

## Safety contract

- No Postgres writes.
- No Qdrant writes.
- No OpenSearch writes.
- No source-truth mutation.
- No answer permission.
- No claim-proof authority.
