# Incremental RAG Embeddings v2

This patch stops the backend from throwing away all RAG embeddings whenever RAG chunks are rebuilt.

## What changed

Before this patch:

```text
build_rag_chunks.py
  dropped rag_chunks
  dropped rag_chunk_fts
  dropped rag_embeddings

build_rag_embeddings.py
  re-embedded every chunk
```

After this patch:

```text
build_rag_chunks.py
  rebuilds chunk tables
  preserves rag_embeddings
  writes a chunk_hash for every chunk

build_rag_embeddings.py
  reuses embeddings when chunk_hash is unchanged
  deletes stale embeddings when chunk text changed
  embeds only missing/stale chunks
```

This makes backend rebuilds much faster after the first full embedding run.

## Test command

```bash
python -m pytest tests/unit/test_tiff_rag_incremental_embedding_reuse.py tests/unit/test_tiff_rag_chunks.py tests/unit/test_tiff_rag_retriever.py -q
```

## Recommended run

```bash
python scripts/run_tiff_backend_pipeline.py --config local_config.yaml
```

On the second run, if no RAG chunks changed, the embedding step should show something like:

```text
Embeddings written: 0
Skipped existing: 538
Stale deleted: 0
```

If a chunk changed, only that changed chunk should be re-embedded.
