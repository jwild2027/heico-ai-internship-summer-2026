# TRACE-Net Page Retrieval Large Eval v1

Builds one retrieval/LLM test question per page for the first N pages of the source package, defaulting to the first 170 pages.

The module reads the source `metadata.zip`, page retrieval profiles, and optionally queries the Qdrant BGE-M3 page-profile collection using local Ollama embeddings. It outputs query records with target page IDs, blank-page expectations, top-k retrieval results, hit-rate metrics, and safety counters.

Safety contract:

- read-only evaluation
- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- no claim-proof authority

Blank pages receive explicit expected behavior: the LLM should say the page is blank or empty.
