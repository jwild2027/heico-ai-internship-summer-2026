# Local TIFF RAG MVP

This add-on turns the existing TIFF search database into a local, source-backed RAG assistant.

It uses the database you already built:

```text
local_data/db/tiff_search.db
```

It does **not** store TIFF image bytes in a vector database. It stores OCR chunks, optional local embeddings, and source pointers back to the TIFF/OCR files.

## What it adds

```text
tiff/ollama_client.py
tiff/rag_chunks.py
tiff/rag_retriever.py
tiff/rag_answer.py
tiff/rag_web_ui.py

scripts/build_rag_chunks.py
scripts/build_rag_embeddings.py
scripts/ask_tiff_rag.py
scripts/serve_tiff_rag_ui.py

tests/unit/test_tiff_rag_chunks.py
tests/unit/test_tiff_rag_retriever.py
tests/unit/test_tiff_rag_answer.py
```

## Recommended Ollama models

From your installed models, start with:

```text
Embedding model: bge-m3:latest
Answer model: llama3.1:8b
```

Good fallback answer models:

```text
gemma3:4b
phi3:mini
```

## Build order

Run from the repo root:

```bash
python scripts/build_tiff_search_index.py --rescarta-export-dir local_data/rescarta_exports --output-db local_data/db/tiff_search.db
python scripts/build_part_catalog.py --db-path local_data/db/tiff_search.db
python scripts/build_rag_chunks.py --db-path local_data/db/tiff_search.db
python scripts/build_rag_embeddings.py --db-path local_data/db/tiff_search.db --model bge-m3:latest
```

The embedding step requires Ollama to be running.

## Ask a question

With the LLM:

```bash
python scripts/ask_tiff_rag.py --db-path local_data/db/tiff_search.db --embed-model bge-m3:latest --llm-model llama3.1:8b "What is part number 120-37313-001?"
```

Without the LLM, source-only/extractive mode:

```bash
python scripts/ask_tiff_rag.py --db-path local_data/db/tiff_search.db --no-llm --no-embeddings "What is part number 120-37313-001?"
```

Expected style of answer:

```text
120-37313-001 is listed as MAGAZINE HOLDER.

Sources:
1. T.P. 120/1176 - ATA 25-21-00 - Page 1311
   TIFF: local_data\rescarta_exports\...
```

## Start the web RAG UI

```bash
python scripts/serve_tiff_rag_ui.py --db-path local_data/db/tiff_search.db --host 127.0.0.1 --port 8090 --embed-model bge-m3:latest --llm-model llama3.1:8b --open
```

Then open:

```text
http://127.0.0.1:8090
```

## How retrieval works

The assistant does not ask the LLM to guess. It retrieves sources first:

```text
1. exact part_catalog match
2. exact part_mentions match
3. keyword OCR chunk match
4. vector search, if embeddings exist
5. local Ollama answer with citations
```

For a question like:

```text
What is part number 120-37313-001?
```

it should use `part_catalog` first and then cite the TIFF page.

## Tables added to tiff_search.db

```text
rag_chunks
rag_chunk_fts
rag_embeddings
```

## Notes

- This is still a SQLite MVP for the 509-page pilot.
- For the future 5 TB system, keep the same logic but move keyword search to OpenSearch and vectors to Qdrant/OpenSearch vector/pgvector.
- The TIFF files remain on disk or in ResCarta. The RAG database stores text chunks, metadata, embeddings, and pointers.
