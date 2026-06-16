# TRACE-Net Real Embeddings with BGE-M3 v1

This patch adds a real local embedding mode to the TRACE-Net Qdrant loaders.

Chosen production/default model:

```text
embedding software/library: sentence-transformers
embedding model: BAAI/bge-m3
vector dimension: 1024
Qdrant distance: Cosine
```

The previous `--embedding-mode hash --embedding-dim 384` mode is still available for deterministic loader smoke tests. For semantic retrieval, use:

```text
--embedding-mode bge-m3
--embedding-model BAAI/bge-m3
--embedding-dim 1024
```

## Install runtime dependencies

```bash
python -m pip install -U "sentence-transformers" "torch"
```

For a corporate or air-gapped deployment, pre-download/cache `BAAI/bge-m3` in an approved internal model cache and set `HF_HOME` or use the local model path with `--embedding-model`.

## Delete/recreate the existing hash-vector Qdrant collections

These commands delete the current hash-vector collections. The loader commands below also use `--recreate`, but explicit deletion makes the swap obvious.

```bash
export QDRANT_URL="http://localhost:6333"

curl -s -X DELETE "$QDRANT_URL/collections/trace_net_embedding_candidates_v1" | python -m json.tool
curl -s -X DELETE "$QDRANT_URL/collections/trace_net_page_retrieval_profiles_v1" | python -m json.tool
```

## Re-embed the 1476 candidate/helper records with BGE-M3

```bash
python scripts/load_trace_net_qdrant_embeddings_v1.py \
  --candidates-path local_data/organization/trace_net/embedding_candidates/trace_net_embedding_candidates_v1.json \
  --output-dir local_data/organization/trace_net/qdrant_loader_bge_m3 \
  --qdrant-url "$QDRANT_URL" \
  --collection trace_net_embedding_candidates_v1 \
  --embedding-mode bge-m3 \
  --embedding-model BAAI/bge-m3 \
  --embedding-dim 1024 \
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

## Re-embed the 509 page retrieval profiles with BGE-M3 and progress

```bash
python scripts/load_trace_net_page_retrieval_profiles_qdrant_v1.py \
  --profiles-path local_data/organization/trace_net/page_retrieval_profiles/trace_net_page_retrieval_profiles_v1.json \
  --output-dir local_data/organization/trace_net/qdrant_page_retrieval_profiles_bge_m3 \
  --qdrant-url "$QDRANT_URL" \
  --collection trace_net_page_retrieval_profiles_v1 \
  --embedding-mode bge-m3 \
  --embedding-model BAAI/bge-m3 \
  --embedding-dim 1024 \
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

## Quality checks

```bash
python scripts/check_trace_net_qdrant_loader_v1_quality.py \
  --manifest-path local_data/organization/trace_net/qdrant_loader_bge_m3/trace_net_qdrant_loader_v1_manifest.json \
  --qdrant-url "$QDRANT_URL" \
  --collection trace_net_embedding_candidates_v1 \
  --require-first-pages 1-50 \
  --min-loaded-points 1476 \
  --min-rag-points 1426 \
  --min-context-helper-points 50 \
  --min-pages-with-points 509 \
  --require-candidate-quality-pass \
  --require-exact-qdrant-count \
  --write-json

python scripts/check_trace_net_page_retrieval_profiles_qdrant_v1_quality.py \
  --manifest-path local_data/organization/trace_net/qdrant_page_retrieval_profiles_bge_m3/trace_net_page_retrieval_profiles_qdrant_v1_manifest.json \
  --qdrant-url "$QDRANT_URL" \
  --collection trace_net_page_retrieval_profiles_v1 \
  --min-loaded-points 509 \
  --min-pages-with-points 509 \
  --min-source-trace-points 509 \
  --min-context-v2-points 50 \
  --require-profile-quality-pass \
  --require-exact-qdrant-count \
  --write-json
```

## Safety contract

BGE-M3 improves semantic retrieval, but it does not change TRACE-Net authority.

```text
Qdrant hit -> Postgres resolution -> citation -> trust authority -> answer gate
```

No vector payload can answer directly, prove claims, mutate source truth, replace citation, or override trust.
