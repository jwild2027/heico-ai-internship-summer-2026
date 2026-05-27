# TIFF RAG Hybrid Retrieval Patch

This patch makes the local TIFF RAG retriever smarter for broad questions.

Before this patch, questions such as:

```text
Summarize the sources related to magazine holder parts.
```

were mostly handled as keyword-only retrieval. That meant the system could miss the structured part catalog and reverse nomenclature resolver even though `magazine holder` maps to `HOLDER, MAGAZINE` in the cleaned catalog.

After this patch, the retriever routes questions by intent:

```text
Exact part number lookup
  -> part_catalog_clean + part_mentions
  -> deterministic answer when catalog data exists

Bare nomenclature / locate question
  -> nomenclature reverse lookup
  -> matching part numbers + pages where those parts appear
  -> deterministic answer

Summary / compare / broad question
  -> hybrid retrieval
  -> part catalog + nomenclature resolver + part mentions + keyword OCR + embeddings when available
  -> LLM summary with citations
```

## New behavior

Exact part lookup stays deterministic:

```bash
python scripts/ask_tiff_rag.py --db-path local_data/db/tiff_search.db --embed-model bge-m3:latest --llm-model gemma3:12B "What is part number 120-37313-001?"
```

Expected:

```text
LLM used: False
Embeddings used: False
120-37313-001 is listed as HOLDER, MAGAZINE.
```

Reverse nomenclature lookup stays deterministic:

```bash
python scripts/ask_tiff_rag.py --db-path local_data/db/tiff_search.db --embed-model bge-m3:latest --llm-model gemma3:12B "Where is magazine holder shown?" --top-k 12
```

Expected:

```text
LLM used: False
Embeddings used: False
I found these part numbers matching that nomenclature:
- 120-36843-001: HOLDER, MAGAZINE
- 120-37313-001: HOLDER, MAGAZINE
- 120-37313-535: HOLDER, MAGAZINE
```

Summary questions now use hybrid retrieval:

```bash
python scripts/ask_tiff_rag.py --db-path local_data/db/tiff_search.db --embed-model bge-m3:latest --llm-model gemma3:12B "Summarize the sources related to magazine holder parts." --top-k 12
```

Expected:

```text
LLM used: True
Embeddings used: True   # if bge-m3 embeddings are present and Ollama is reachable
```

If embeddings are not built or Ollama is not reachable, the system still uses catalog, nomenclature, part mentions, and keyword OCR.

## New command options

`ask_tiff_rag.py` now supports:

```text
--answer-mode auto|lookup|locate|summarize|compare
--retrieval-mode auto|structured|keyword|semantic|hybrid
--force-llm
--force-embeddings
```

Examples:

```bash
python scripts/ask_tiff_rag.py --db-path local_data/db/tiff_search.db --llm-model gemma3:12B --answer-mode summarize --retrieval-mode hybrid "Summarize the sources related to magazine holder parts." --top-k 12
```

```bash
python scripts/ask_tiff_rag.py --db-path local_data/db/tiff_search.db --llm-model gemma3:12B --force-embeddings "What information is available about passenger seat back?" --top-k 12
```

## Files added or patched

```text
tiff/rag_router.py
tiff/rag_retriever.py
tiff/rag_answer.py
tiff/rag_web_ui.py
scripts/ask_tiff_rag.py
tests/unit/test_tiff_rag_hybrid_routing.py
```

## Test command

```bash
python -m pytest tests/unit/test_tiff_rag_hybrid_routing.py tests/unit/test_tiff_rag_reverse_lookup_balanced_sources.py tests/unit/test_tiff_rag_nomenclature_reverse_lookup.py tests/unit/test_tiff_rag_source_grouping.py tests/unit/test_tiff_rag_answer.py tests/unit/test_tiff_rag_retriever.py -q
```

In the package build environment this passed along with the full unit suite.
