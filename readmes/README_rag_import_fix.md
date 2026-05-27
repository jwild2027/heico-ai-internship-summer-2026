# Local RAG MVP import-path fix

This patch fixes direct Windows script execution for the RAG scripts.

The previous files worked under pytest but could fail when run directly like:

```bash
python scripts/build_rag_chunks.py --db-path local_data/db/tiff_search.db
```

because Python started with `scripts/` on the import path instead of the repo root.

This patch adds the repo root to `sys.path` in:

```text
scripts/build_rag_chunks.py
scripts/build_rag_embeddings.py
scripts/ask_tiff_rag.py
scripts/serve_tiff_rag_ui.py
```

After unzipping, resume from the failed command:

```bash
python scripts/build_rag_chunks.py --db-path local_data/db/tiff_search.db
python scripts/build_rag_embeddings.py --db-path local_data/db/tiff_search.db --model bge-m3:latest
python scripts/ask_tiff_rag.py --db-path local_data/db/tiff_search.db --embed-model bge-m3:latest --llm-model llama3.1:8b "What is part number 120-37313-001?"
```
