# Local RAG script fix v2

This patch replaces the four RAG command scripts with versions that:

- add the project root to `sys.path` before importing `tiff.*`
- match the `RagChunkBuildSummary` and `EmbeddingBuildSummary` objects in the RAG MVP modules
- keep the original command-line flags: `--ollama-url`, `--top-k`, and `--no-embeddings`

Resume after installing with:

```bash
python scripts/build_rag_chunks.py --db-path local_data/db/tiff_search.db
python scripts/build_rag_embeddings.py --db-path local_data/db/tiff_search.db --model bge-m3:latest
python scripts/ask_tiff_rag.py --db-path local_data/db/tiff_search.db --embed-model bge-m3:latest --llm-model llama3.1:8b "What is part number 120-37313-001?"
```
