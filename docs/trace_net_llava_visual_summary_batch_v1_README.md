# TRACE-Net LLaVA Visual Summary Batch v1

Patch B module for the image/visual route. It consumes the Patch A image-route LLaVA jobs JSONL and writes structured visual observation cards. The module can run in `dry_run` mode for CI/smoke tests or `ollama` mode against local `llava:13b`.

Safety contract: no Postgres writes, no Qdrant writes, no OpenSearch writes/uploads, no source-truth mutation, and no answer permission.

Authority rule: LLaVA sees/describes visual content. OCR/table/figure-item evidence proves part identity and final factual claims.
