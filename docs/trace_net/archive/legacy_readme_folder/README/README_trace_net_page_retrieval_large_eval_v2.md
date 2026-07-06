# TRACE-Net Page Retrieval Large Eval v2

Creates one retrieval and graph-path-constrained LLM test card per page. The artifact measures Qdrant BGE-M3 page routing when requested, but it also requires the LLM-facing answer plan to follow the approved page graph path:

```text
Page -> SourceLink / Dublin Core source package entry -> retrieval evidence -> final gate
```

Safety contract:

- no Postgres writes
- no Qdrant writes
- no OpenSearch writes
- no source-truth mutation
- no answer permission
- no claim-proof authority

This module is an eval/planning layer. It does not answer user questions directly.

## Query embedding cache

The full Qdrant eval embeds generated query text with Ollama before searching Qdrant. This is separate from corpus embedding: it does not rewrite the 509 page-profile vectors. Use `--use-query-embedding-cache` to store/reuse query vectors in a local JSONL cache:

```bash
python scripts/build_trace_net_page_retrieval_large_eval_v2.py \
  ... \
  --run-qdrant-eval \
  --use-query-embedding-cache \
  --query-embedding-cache-path local_data/organization/trace_net/page_retrieval_large_eval_v2/query_embedding_cache_ollama_bge_m3.jsonl
```

The cache key includes the schema version, embedding source, model name, and query text. If query text or model changes, the module creates a new cache entry. Use `--reset-query-embedding-cache` to rebuild the cache from scratch.

Summary counters include:

```text
query_embedding_cache_enabled
query_embedding_cache_hit_count
query_embedding_cache_miss_count
query_embedding_cache_write_count
query_embedding_ollama_request_count
```
