# RAG source-link exact lookup fix

This patch fixes two issues found after source-link integration:

1. Exact part-number lookups should remain deterministic even when `local_config.yaml` has `retrieval_mode: hybrid`.
   - `What is part number 120-37313-001?` should not use embeddings unless `--force-embeddings` is passed.
   - Keyword/vector supplemental pages are not added to exact part lookup source lists.

2. Existing pipeline-quality unit tests are updated to include the new `source_links` table count.

It also prints ResCarta/source URLs in the CLI `Sources:` block when available.
