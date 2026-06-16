# TRACE-Net Ollama Embeddings v1

This patch adds a local Ollama embedding backend to the TRACE-Net Qdrant loaders.
It avoids Hugging Face downloads and corporate SSL certificate issues by calling
Ollama on localhost.

Supported embedding modes now include:

```text
--embedding-mode hash
--embedding-mode sentence-transformers
--embedding-mode bge-m3
--embedding-mode ollama
```

The Ollama path uses:

```text
Default URL:      http://localhost:11434
Default endpoint: /api/embed
Default model:    bge-m3:latest
```

The Qdrant payload safety contract is unchanged. Ollama/Qdrant vectors are only
retrieval signals. They are not source truth, not answer authority, and not claim
proof.

## Candidate/helper collection

```bash
export QDRANT_URL="http://localhost:6333"
export OLLAMA_URL="http://localhost:11434"

python scripts/load_trace_net_qdrant_embeddings_v1.py \
  --candidates-path local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json \
  --output-dir local_data/organization/trace_net/qdrant_loader_ollama_bge_m3 \
  --qdrant-url "$QDRANT_URL" \
  --collection trace_net_embedding_candidates_v1 \
  --embedding-mode ollama \
  --embedding-model bge-m3:latest \
  --embedding-dim 1024 \
  --ollama-url "$OLLAMA_URL" \
  --batch-size 64 \
  --recreate \
  --require-first-pages 1-50 \
  --min-loaded-points 1476 \
  --min-rag-points 1426 \
  --min-context-helper-points 50 \
  --min-pages-with-points 509 \
  --require-candidate-quality-pass \
  --require-exact-qdrant-count \
  --quality
```

## Page profile collection

```bash
python scripts/load_trace_net_page_retrieval_profiles_qdrant_v1.py \
  --profiles-path local_data/organization/trace_net/page_retrieval_profiles/trace_net_page_retrieval_profiles_v1.json \
  --output-dir local_data/organization/trace_net/qdrant_page_retrieval_profiles_ollama_bge_m3 \
  --qdrant-url "$QDRANT_URL" \
  --collection trace_net_page_retrieval_profiles_v1 \
  --embedding-mode ollama \
  --embedding-model bge-m3:latest \
  --embedding-dim 1024 \
  --ollama-url "$OLLAMA_URL" \
  --batch-size 64 \
  --progress \
  --progress-every 25 \
  --recreate \
  --min-loaded-points 509 \
  --min-pages-with-points 509 \
  --min-source-trace-points 509 \
  --min-context-v2-points 50 \
  --require-profile-quality-pass \
  --require-exact-qdrant-count \
  --quality
```

## Legacy endpoint fallback

If an older Ollama server only exposes `/api/embeddings`, pass:

```bash
--ollama-endpoint /api/embeddings
```

## Safety invariant

```text
Ollama creates vectors.
Qdrant stores/searches vectors.
Postgres graph/source/trust/citation remains answer authority.
```
